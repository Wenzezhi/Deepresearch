<template><div class="chat-markdown" v-html="html"></div></template>
<script setup lang="ts">
import {computed} from 'vue';
import {marked} from 'marked';
import DOMPurify from 'dompurify';
const props=defineProps<{content:string}>();
const html=computed(()=>{
  const rendered=marked.parse(props.content,{async:false,gfm:true});
  const clean=DOMPurify.sanitize(rendered,{USE_PROFILES:{html:true},FORBID_TAGS:['style','form','input','button','iframe','img','video','audio'],FORBID_ATTR:['style','id','name'],ALLOW_DATA_ATTR:false});
  const template=document.createElement('template');template.innerHTML=clean;
  template.content.querySelectorAll('a').forEach(link=>{const href=link.getAttribute('href')||'';if(!/^(https?:\/\/|mailto:|#)/i.test(href))link.removeAttribute('href');else{link.target='_blank';link.rel='noopener noreferrer';}});
  return template.innerHTML;
});
</script>
<style scoped>
.chat-markdown{white-space:normal;line-height:1.8;font-size:14px;color:#34435c;overflow-wrap:anywhere;min-width:0}.chat-markdown :deep(> :first-child){margin-top:0}.chat-markdown :deep(> :last-child){margin-bottom:0}.chat-markdown :deep(p){margin:10px 0}.chat-markdown :deep(h1),.chat-markdown :deep(h2),.chat-markdown :deep(h3),.chat-markdown :deep(h4){color:#25344e;font-weight:650;line-height:1.5;margin:18px 0 10px}.chat-markdown :deep(h1){font-size:21px}.chat-markdown :deep(h2){font-size:18px}.chat-markdown :deep(h3),.chat-markdown :deep(h4){font-size:16px}.chat-markdown :deep(strong){color:#203453}.chat-markdown :deep(ul),.chat-markdown :deep(ol){padding-left:22px;margin:10px 0}.chat-markdown :deep(li){margin:5px 0}.chat-markdown :deep(a){color:#356ed9;text-decoration:none}.chat-markdown :deep(a:hover){text-decoration:underline}.chat-markdown :deep(blockquote){margin:12px 0;padding:8px 12px;border-left:3px solid #9bb8ed;background:#f4f7fd;color:#6d7e98}.chat-markdown :deep(code){font-family:Consolas,monospace;font-size:.9em;background:#eef3fc;border-radius:4px;padding:2px 5px}.chat-markdown :deep(pre){white-space:pre;overflow-x:auto;max-width:100%;padding:12px;box-sizing:border-box;border:1px solid #dfe7f4;border-radius:8px;background:#f5f8fe;line-height:1.6}.chat-markdown :deep(pre code){padding:0;background:none;border-radius:0}.chat-markdown :deep(table){display:block;max-width:100%;overflow-x:auto;border-collapse:collapse;font-size:13px;margin:12px 0}.chat-markdown :deep(th),.chat-markdown :deep(td){border:1px solid #dce5f3;padding:8px 10px;text-align:left;min-width:60px}.chat-markdown :deep(th){background:#f1f2f4;color:#424954}.chat-markdown :deep(hr){border:0;border-top:1px solid #e1e8f3;margin:16px 0}
</style>
