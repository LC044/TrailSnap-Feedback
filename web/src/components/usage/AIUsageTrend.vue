<template>
  <article class="panel trend">
    <div class="trend-head"><h3>{{ title }}</h3><el-select v-model="metric" :aria-label="`${title}指标`" class="metric"><el-option v-for="item in series" :key="item.key" :label="item.label" :value="item.key" /></el-select></div>
    <div v-if="values.length" class="chart">
      <div class="axis" aria-hidden="true"><span>{{ format(max) }}</span><span>{{ format(max/2) }}</span><span>0</span></div>
      <svg viewBox="0 0 640 144" preserveAspectRatio="none" role="img" :aria-label="`${label}折线图`">
        <path class="grid" d="M0 1H640 M0 72H640 M0 143H640" />
        <path :d="area" class="area" />
        <polyline :points="points" class="line" />
      </svg>
    </div>
    <div v-if="rows.length" class="axis-date" aria-hidden="true"><span>{{ rows[0]?.day.slice(5) }}</span><span>{{ rows[Math.floor(rows.length / 2)]?.day.slice(5) }}</span><span>{{ rows[rows.length - 1]?.day.slice(5) }}</span></div>
    <details v-if="rows.length"><summary>查看每日数据</summary><div class="data-scroll"><table><thead><tr><th>日期</th><th>{{ label }}</th></tr></thead><tbody><tr v-for="(row,i) in rows" :key="row.day"><td>{{ row.day }}</td><td>{{ values[i]?.toLocaleString('zh-CN') }}</td></tr></tbody></table></div></details>
  </article>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { OverviewCounts } from '../../api/aiUsage'

type Metric = keyof OverviewCounts | 'total_tokens'
const props = defineProps<{title:string;rows:(OverviewCounts & {day:string})[];series:readonly {key:Metric;label:string}[]}>()
const metric = ref<Metric>(props.series[0]?.key ?? 'turns')
const label = computed(() => props.series.find(item => item.key === metric.value)?.label ?? '')
const values = computed(() => props.rows.map(row => metric.value === 'total_tokens' ? row.input_tokens + row.output_tokens : row[metric.value]))
const max = computed(() => Math.max(2, Math.ceil(Math.max(0,...values.value) / 2) * 2))
const points = computed(() => values.value.map((value, i) => `${640*i/Math.max(1,values.value.length-1)},${143-142*value/max.value}`).join(' '))
const area = computed(() => points.value ? `M0,143 L${points.value} L640,143 Z` : '')
const format = (n:number) => Intl.NumberFormat('zh-CN',{notation:'compact',maximumFractionDigits:1}).format(n)
</script>
<style scoped>
.trend{min-width:0;padding:14px}.trend-head{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}.trend-head h3{margin:0;font-size:16px}.metric{width:132px}.chart{display:grid;grid-template-columns:42px minmax(0,1fr);height:144px}.axis{display:flex;flex-direction:column;justify-content:space-between;text-align:right;padding-right:8px}.axis-date{display:flex;justify-content:space-between;margin:4px 0 0 42px}.axis,.axis-date,summary,.data-scroll{font-size:12px;color:var(--rp-text-3)}svg{width:100%;height:100%;overflow:visible}.grid{stroke:var(--rp-border)}.line{stroke:var(--rp-primary);stroke-width:2.2;fill:none;vector-effect:non-scaling-stroke}.area{fill:var(--rp-primary);opacity:.11}details{margin-top:8px}summary{cursor:pointer}.data-scroll{max-height:190px;overflow:auto;margin-top:5px}table{width:100%;text-align:left;border-collapse:collapse}th,td{padding:4px;border-bottom:1px solid var(--rp-border)}
</style>
