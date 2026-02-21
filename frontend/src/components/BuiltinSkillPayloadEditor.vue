<template>
  <div class="skillPayloadEditor" :data-depth="depth">
    <template v-if="isObjectValue">
      <div v-for="[key, child] in objectEntries" :key="`${depth}-${key}`" class="payloadField">
        <div class="payloadFieldLabel">{{ key }}</div>
        <div class="payloadFieldBody">
          <template v-if="isComplexValue(child)">
            <BuiltinSkillPayloadEditor
              :model-value="child"
              :depth="depth + 1"
              @update:model-value="(next) => updateObjectChild(key, next)"
            />
          </template>
          <template v-else-if="isPptStyleField(key)">
            <select
              class="input"
              :value="toText(child) || 'auto'"
              @change="updateObjectChild(key, ($event.target as HTMLSelectElement).value)"
            >
              <option value="auto">auto（自动）</option>
              <option value="modern_blue">modern_blue（现代蓝）</option>
              <option value="minimal_gray">minimal_gray（极简灰）</option>
              <option value="dark_tech">dark_tech（深色科技）</option>
              <option value="warm_business">warm_business（暖色商务）</option>
              <option value="template_jetlinks">template_jetlinks（科技蓝模板）</option>
              <option value="template_team">template_team（企业蓝模板）</option>
            </select>
          </template>
          <template v-else-if="isPptLayoutModeField(key)">
            <select
              class="input"
              :value="toText(child) || 'auto'"
              @change="updateObjectChild(key, ($event.target as HTMLSelectElement).value)"
            >
              <option value="auto">auto（自动）</option>
              <option value="focus">focus（聚焦）</option>
              <option value="single_column">single_column（单栏）</option>
              <option value="two_column">two_column（双栏）</option>
              <option value="cards">cards（卡片）</option>
            </select>
          </template>
          <template v-else-if="typeof child === 'boolean'">
            <label class="chip">
              <input
                type="checkbox"
                :checked="child"
                @change="updateObjectChild(key, ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ child ? "true" : "false" }}</span>
            </label>
          </template>
          <template v-else-if="typeof child === 'number'">
            <input
              class="input"
              type="number"
              :value="String(child)"
              @input="updateObjectChild(key, parseNumber(($event.target as HTMLInputElement).value, child))"
            />
          </template>
          <template v-else>
            <textarea
              v-if="isLongTextValue(child)"
              class="textarea payloadTextarea"
              :value="toText(child)"
              @input="updateObjectChild(key, ($event.target as HTMLTextAreaElement).value)"
            />
            <input
              v-else
              class="input"
              :value="toText(child)"
              @input="updateObjectChild(key, ($event.target as HTMLInputElement).value)"
            />
          </template>
        </div>
      </div>
    </template>

    <template v-else-if="isArrayValue">
      <div class="payloadArrayHead">
        <span class="subtle">数组（{{ arrayValue.length }}）</span>
        <button class="ghostBtn payloadArrayBtn" type="button" @click="appendArrayItem">+ 添加</button>
      </div>

      <div v-if="arrayValue.length === 0" class="subtle">空数组</div>
      <div v-for="(item, index) in arrayValue" :key="`${depth}-${index}`" class="payloadArrayItem">
        <div class="payloadArrayItemHead">
          <span class="payloadArrayIndex">#{{ index + 1 }}</span>
          <button class="ghostBtn payloadArrayBtn" type="button" @click="removeArrayItem(index)">删除</button>
        </div>

        <div class="payloadArrayItemBody">
          <template v-if="isComplexValue(item)">
            <BuiltinSkillPayloadEditor
              :model-value="item"
              :depth="depth + 1"
              @update:model-value="(next) => updateArrayItem(index, next)"
            />
          </template>
          <template v-else-if="typeof item === 'boolean'">
            <label class="chip">
              <input
                type="checkbox"
                :checked="item"
                @change="updateArrayItem(index, ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ item ? "true" : "false" }}</span>
            </label>
          </template>
          <template v-else-if="typeof item === 'number'">
            <input
              class="input"
              type="number"
              :value="String(item)"
              @input="updateArrayItem(index, parseNumber(($event.target as HTMLInputElement).value, item))"
            />
          </template>
          <template v-else>
            <textarea
              v-if="isLongTextValue(item)"
              class="textarea payloadTextarea"
              :value="toText(item)"
              @input="updateArrayItem(index, ($event.target as HTMLTextAreaElement).value)"
            />
            <input
              v-else
              class="input"
              :value="toText(item)"
              @input="updateArrayItem(index, ($event.target as HTMLInputElement).value)"
            />
          </template>
        </div>
      </div>
    </template>

    <template v-else>
      <input
        class="input"
        :value="toText(modelValue)"
        @input="emitValue(($event.target as HTMLInputElement).value)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"

defineOptions({ name: "BuiltinSkillPayloadEditor" })

const props = withDefaults(
  defineProps<{
    modelValue: unknown
    depth?: number
  }>(),
  {
    depth: 0,
  },
)

const emit = defineEmits<{
  (event: "update:modelValue", value: unknown): void
}>()

const depth = computed(() => Math.max(0, Number(props.depth || 0)))

const isArrayValue = computed(() => Array.isArray(props.modelValue))

const isObjectValue = computed(() => isPlainObject(props.modelValue))

const objectEntries = computed(() => {
  if (!isObjectValue.value) return [] as Array<[string, unknown]>
  return Object.entries(props.modelValue as Record<string, unknown>)
})

const arrayValue = computed(() => (Array.isArray(props.modelValue) ? (props.modelValue as unknown[]) : []))

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function isComplexValue(value: unknown): boolean {
  return Array.isArray(value) || isPlainObject(value)
}

function isPptPayloadRoot(): boolean {
  if (!isPlainObject(props.modelValue)) return false
  const slides = (props.modelValue as Record<string, unknown>).slides
  return Array.isArray(slides)
}

function isPptStyleField(key: string): boolean {
  return key === "style" && isPptPayloadRoot()
}

function isPptLayoutModeField(key: string): boolean {
  return key === "layout_mode" && isPptPayloadRoot()
}

function emitValue(next: unknown) {
  emit("update:modelValue", next)
}

function cloneValue<T>(value: T): T {
  try {
    if (typeof structuredClone === "function") return structuredClone(value)
  } catch {
    // ignore
  }
  try {
    return JSON.parse(JSON.stringify(value)) as T
  } catch {
    return value
  }
}

function parseNumber(raw: string, fallback: number): number {
  const value = raw.trim()
  if (!value) return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function toText(value: unknown): string {
  if (typeof value === "string") return value
  if (value == null) return ""
  return String(value)
}

function isLongTextValue(value: unknown): boolean {
  const text = toText(value)
  return text.includes("\n") || text.length >= 60
}

function updateObjectChild(key: string, next: unknown) {
  const current = isObjectValue.value ? { ...(props.modelValue as Record<string, unknown>) } : {}
  current[key] = next
  emitValue(current)
}

function updateArrayItem(index: number, next: unknown) {
  const current = arrayValue.value.slice()
  if (index < 0 || index >= current.length) return
  current[index] = next
  emitValue(current)
}

function removeArrayItem(index: number) {
  const current = arrayValue.value.slice()
  if (index < 0 || index >= current.length) return
  current.splice(index, 1)
  emitValue(current)
}

function appendArrayItem() {
  const current = arrayValue.value.slice()
  let seed: unknown = ""
  if (current.length > 0) {
    const first = current[0]
    if (typeof first === "number") seed = 0
    else if (typeof first === "boolean") seed = false
    else if (isComplexValue(first)) seed = cloneValue(first)
  }
  current.push(seed)
  emitValue(current)
}
</script>

<style scoped>
.skillPayloadEditor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloadField {
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  background: var(--surfaceSolid);
  padding: 8px;
}

.payloadFieldLabel {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 6px;
  font-weight: 700;
}

.payloadFieldBody {
  min-width: 0;
}

.payloadArrayHead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.payloadArrayItem {
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  padding: 8px;
}

.payloadArrayItemHead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.payloadArrayIndex {
  font-size: 11px;
  color: var(--muted);
  font-weight: 700;
}

.payloadArrayItemBody {
  min-width: 0;
}

.payloadArrayBtn {
  height: 28px;
  padding: 0 9px;
  font-size: 11px;
  border-radius: 8px;
}

.payloadTextarea {
  min-height: 92px;
  height: auto;
}

.skillPayloadEditor[data-depth="0"] .payloadField {
  background: linear-gradient(180deg, var(--surfaceSolid), var(--surface2));
}
</style>
