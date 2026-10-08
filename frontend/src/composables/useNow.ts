import { onScopeDispose, ref } from 'vue'

/** Current time in ms, refreshed every intervalMs; for "N seconds ago" labels. */
export function useNow(intervalMs = 1_000) {
  const now = ref(Date.now())
  const timer = setInterval(() => (now.value = Date.now()), intervalMs)
  onScopeDispose(() => clearInterval(timer))
  return now
}
