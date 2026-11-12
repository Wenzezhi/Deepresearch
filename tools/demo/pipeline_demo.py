"""走一遍真实研究流程生成演示数据，然后用质检接口审计它。

关键点：报告不是硬编码进数据库的，而是由后端研究流程（规划→检索→总结→报告）
真实产出的；模型换成本地 mock，只是为了在外网模型不稳定时保证可重复演示。
"""
import json
import time

import requests

BASE = "http://127.0.0.1:8000"
MOCK = "http://127.0.0.1:8099"
TOPIC = "多模态大模型在 2025 年的关键突破"

session = requests.Session()
session.get(MOCK + "/healthz", timeout=5).raise_for_status()

# 1. 准备演示用模型配置（指向本地 mock，OpenAI 兼容）
profiles = session.get(BASE + "/model-profiles", timeout=10).json()
demo = next((p for p in profiles if p.get("name") == "演示模型（Mock）"), None)
payload = {
    "name": "演示模型（Mock）",
    "base_url": MOCK + "/v1",
    "model_id": "mock-research",
    "api_key": "mock-key",
    "max_tokens": 8192,
    "timeout": 60,
}
if demo:
    profile_id = demo["id"]
    session.put(f"{BASE}/model-profiles/{profile_id}", json=payload, timeout=20)
else:
    profile_id = session.post(BASE + "/model-profiles", json=payload, timeout=20).json()["id"]
print("profile:", profile_id)

# 2. 通过真实研究接口跑一次研究
response = session.post(
    BASE + "/research-runs",
    json={"topic": TOPIC, "model_profile_id": profile_id},
    timeout=30,
)
print("start:", response.status_code)
run_id = response.json()["id"]
print("run:", run_id)

cursor = 0
status = "running"
deadline = time.time() + 600
while time.time() < deadline:
    time.sleep(3)
    detail = session.get(
        BASE + f"/research-runs/{run_id}", params={"after": cursor}, timeout=20
    ).json()
    status = detail["record"]["status"]
    batch = detail.get("events") or []
    if batch:
        cursor = detail.get("next_cursor") or cursor
        for item in batch:
            event = item["event"]
            if event.get("type") in ("task_status", "phase", "error", "final_report", "sources"):
                label = event.get("status") or event.get("phase") or event.get("type")
                print(f"  [{event.get('type')}] {label}", flush=True)
    if status != "running":
        break

print("final status:", status)

# 3. 质检这次真实产出的 run
audit = session.get(BASE + f"/quality/audit/{run_id}", timeout=60).json()
print("\n=== 质检结果 ===")
print("report_available:", audit["report_available"], "| score:", audit["score"], "| grade:", audit["grade"])
print("metrics:", json.dumps(
    {k: audit["metrics"][k] for k in (
        "cited_links", "inline_citations", "cited_unique", "retrieved_unique",
        "verified", "unverified", "uncited", "coverage", "sections_without_source")},
    ensure_ascii=False))
print("issues:")
for issue in audit["issues"]:
    print("  -", issue["severity"], issue["type"], "|", issue.get("section", ""), "|",
          issue["message"][:60])
print("citations:", len(audit["citations"]), "| sources:", len(audit["sources"]))

# 4. 清理上一版用固定 fixture 造的演示数据
try:
    session.delete(BASE + "/research-runs/qualitydemo0001", timeout=10)
    print("\nremoved old fixture demo run")
except Exception as exc:  # noqa: BLE001
    print("old demo cleanup:", str(exc)[:80])

print("\nDEMO_RUN_ID=" + run_id)
