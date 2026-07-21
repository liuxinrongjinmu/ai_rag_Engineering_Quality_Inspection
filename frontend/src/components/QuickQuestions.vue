<!--
  快捷问题组件
  展示预设高频问题，点击即可发送
-->
<template>
  <div class="quick-questions">
    <div class="quick-questions-title">
      <el-icon><PieChart /></el-icon>
      <span>试试问我</span>
    </div>
    <div class="quick-questions-list">
      <div
        v-for="(q, index) in questions"
        :key="index"
        class="quick-question-item"
        @click="$emit('select', q)"
      >
        <el-icon :size="14"><Promotion /></el-icon>
        <span>{{ q }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * Emits 定义
 * 点击问题卡片时发出 'select' 事件，携带问题文本
 */
defineEmits(['select'])

/**
 * 预设高频问题列表
 */
const questions = [
  '高速公路和一级公路上路床的压实度要求不低于多少？',
  '关键项目的合格率应不低于多少？',
  '土方路基每200m每压实层施工自检测几处？',
  '钢筋原材施工自检每批不超过多少吨？',
  '无机结合料稳定细粒材料最大粒径不超过多少？',
  '公路工程检测机构等级分为哪几类？',
]
</script>

<style scoped>
/* ==================== 容器 ==================== */
.quick-questions {
  padding: 20px 0;
}

.quick-questions-title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

/* ==================== 问题列表 ==================== */
.quick-questions-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.quick-question-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 20px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.quick-question-item:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: #ecf5ff;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}

.quick-question-item:active {
  transform: translateY(0);
}

.quick-question-item .el-icon {
  color: var(--primary-color);
  flex-shrink: 0;
}
</style>
