<template><div class="resize-handle" role="separator" tabindex="0" aria-orientation="vertical" :aria-label="label" :aria-valuenow="Math.round(value)" :aria-valuemin="min" :aria-valuemax="max" @pointerdown="start" @pointermove="move" @pointerup="stop" @pointercancel="stop" @lostpointercapture="stop" @keydown.left.prevent="adjust(-16)" @keydown.right.prevent="adjust(16)"><span aria-hidden="true">↔</span></div></template>
<script setup lang="ts">
import {ref} from 'vue';
const props=withDefaults(defineProps<{label:string;value:number;min:number;max:number;reverse?:boolean}>(),{reverse:false});const emit=defineEmits<{resize:[width:number]}>();const dragging=ref(false);let origin=0;let initial=0;
function adjust(delta:number){emit('resize',Math.max(props.min,Math.min(props.max,props.value+delta*(props.reverse?-1:1))));}
function start(e:PointerEvent){if(e.button!==0)return;e.preventDefault();origin=e.clientX;initial=props.value;dragging.value=true;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);}
function move(e:PointerEvent){if(dragging.value)emit('resize',Math.max(props.min,Math.min(props.max,initial+(e.clientX-origin)*(props.reverse?-1:1))));}
function stop(){dragging.value=false;}
</script>
<style scoped>.resize-handle{width:10px;min-width:10px;align-self:stretch;position:relative;cursor:col-resize;touch-action:none;user-select:none;z-index:5;flex-shrink:0;outline:none;background:transparent}.resize-handle:before{content:'';position:absolute;left:4px;top:0;bottom:0;width:2px;background:#dce6fa}.resize-handle span{position:absolute;top:42%;left:-4px;width:18px;height:30px;border:1px solid #b1c8f5;border-radius:9px;background:#f4f8ff;color:#4777d6;display:grid;place-items:center;font-size:14px}.resize-handle:hover:before,.resize-handle:focus:before{background:#5886ed}.resize-handle:focus span{outline:2px solid #5689ff}</style>
