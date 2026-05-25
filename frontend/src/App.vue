<template>
  <div class="h-screen flex flex-col bg-slate-100 text-slate-900">
    <!-- Topbar -->
    <header class="border-b border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div class="flex items-center gap-3">
        <!-- В Vite public/ доступен по корню: /ico.png -->
        <img src="/ico.png" alt="ico" class="h-10 w-10" />

        <div>
          <div class="text-lg font-bold leading-none">ИИ-Детектор</div>
          <div class="text-xs text-slate-500 leading-none mt-1">Carry-Out MVP</div>
        </div>

        <div class="ml-6 flex items-center gap-2">
          <button
            @click="tab='cameras'"
            class="rounded-xl px-4 py-2 text-sm font-medium transition"
            :class="tab === 'cameras'
              ? 'bg-indigo-600 text-white shadow'
              : 'bg-slate-100 hover:bg-slate-200 text-slate-700'"
          >
            Камеры
          </button>

          <button
            @click="tab='alerts'"
            class="rounded-xl px-4 py-2 text-sm font-medium transition"
            :class="tab === 'alerts'
              ? 'bg-indigo-600 text-white shadow'
              : 'bg-slate-100 hover:bg-slate-200 text-slate-700'"
          >
            Уведомления
          </button>

          <button
            @click="tab='dashboard'"
            class="rounded-xl px-4 py-2 text-sm font-medium transition"
            :class="tab === 'dashboard'
              ? 'bg-indigo-600 text-white shadow'
              : 'bg-slate-100 hover:bg-slate-200 text-slate-700'"
          >
            Дашборд
          </button>
        </div>

        <div class="flex-1"></div>

        <label class="cursor-pointer rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-2 text-sm hover:bg-slate-100 transition">
          <span class="font-medium">Загрузить видео</span>
          <input type="file" multiple accept="video/mp4,video/avi,video/mov" @change="onUpload" class="hidden" />
        </label>
      </div>
    </header>

    <main class="flex-1 overflow-auto">
      <!-- Cameras -->
      <section v-if="tab==='cameras'" class="p-5">
        <div v-if="cameras.length===0" class="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center shadow-sm">
          <div class="text-lg font-semibold">Нет подключённых камер</div>
          <div class="mt-2 text-sm text-slate-500">Загрузите несколько видео</div>
        </div>

        <div v-else class="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
          <div v-for="cam in cameras" :key="cam.camera_id" class="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
            <div class="flex items-start justify-between p-4">
              <div>
                <div class="flex items-center gap-2">
                  <div class="h-2.5 w-2.5 rounded-full" :class="cam.status === 'running' ? 'bg-emerald-500' : 'bg-slate-400'"></div>
                  <div class="font-semibold">Камера {{ cam.camera_id }}</div>
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ cam.status }} · {{ cam.w }}×{{ cam.h }} · {{ Number(cam.fps_src || 0).toFixed(1) }} fps
                </div>
              </div>

              <div class="flex gap-2">
                <button
                  @click="openViewer(cam)"
                  class="rounded-xl bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 transition hover:bg-indigo-100"
                >
                  Увеличить
                </button>

                <button
                  @click="stopCamera(cam.camera_id)"
                  :disabled="cam.status!=='running'"
                  class="rounded-xl bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-100 disabled:opacity-40"
                >
                  Стоп
                </button>
              </div>
            </div>

            <div class="aspect-video overflow-hidden bg-black">
              <img :src="streamUrl(cam.camera_id)" class="h-full w-full object-contain" />
            </div>

            <div class="flex items-center justify-between p-4">
              <a :href="annotUrl(cam.camera_id)" target="_blank" class="text-xs text-slate-500 hover:text-slate-700">
                Annotated stream
              </a>
            </div>
          </div>
        </div>
      </section>

      <!-- Alerts -->
      <section v-else-if="tab==='alerts'" class="p-5">
        <div class="rounded-3xl bg-white p-5 shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="text-2xl font-bold">Уведомления</div>
              <div class="text-sm text-slate-500">События carry-out/exit-zone</div>
            </div>

            <div class="flex items-center gap-3">
              <select v-model="ackFilter" class="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm shadow-sm outline-none">
                <option value="unacked">Только новые</option>
                <option value="all">Все</option>
                <option value="ack">ACK</option>
                <option value="false">False alarm</option>
              </select>

              <button @click="refreshEvents()" class="rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow transition hover:bg-indigo-700">
                Обновить
              </button>
            </div>
          </div>
        </div>

        <div v-if="events.length===0" class="mt-5 rounded-3xl bg-white p-10 text-center shadow-sm">
          <div class="text-lg font-semibold">Нет событий</div>
          <div class="mt-2 text-sm text-slate-500">Ждём обнаружения</div>
        </div>

        <div v-else class="mt-5 space-y-4">
          <div v-for="e in events" :key="e.id" class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="flex items-center gap-3">
                  <div class="text-lg font-semibold">Камера {{ e.camera_id }}</div>

                  <span class="rounded-full px-2.5 py-1 text-xs font-semibold"
                    :class="e.severity === 'warn' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'">
                    {{ e.severity }}
                  </span>

                  <span class="rounded-full px-2.5 py-1 text-xs font-semibold"
                    :class="e.ack_status === 'unacked' ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'">
                    {{ e.ack_status }}
                  </span>
                </div>

                <div class="mt-1 text-sm text-slate-500">{{ e.event_type }}</div>
              </div>

              <div class="text-xs text-slate-400">{{ formatTs(e.ts) }}</div>
            </div>

            <div class="mt-4 text-sm leading-relaxed text-slate-700">{{ e.text }}</div>

            <div class="mt-5 flex flex-wrap items-center gap-3">
              <a
                v-if="e.snapshot_path"
                :href="API_BASE + e.snapshot_path"
                target="_blank"
                class="rounded-xl border border-slate-200 px-4 py-2 text-sm hover:bg-slate-100"
              >
                Открыть скриншот
              </a>

              <div class="flex-1"></div>

              <button
                @click="ackEvent(e.id, 'ack')"
                :disabled="e.ack_status !== 'unacked'"
                class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-40"
              >
                Реагировать
              </button>

              <button
                @click="ackEvent(e.id, 'false')"
                :disabled="e.ack_status !== 'unacked'"
                class="rounded-xl bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-700 disabled:opacity-40"
              >
                Ложная тревога
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Dashboard -->
      <section v-else class="p-5">
        <div class="rounded-3xl bg-white p-5 shadow-sm">
          <div class="flex flex-wrap items-center gap-4">
            <div>
              <div class="text-2xl font-bold">Аналитика</div>
              <div class="text-sm text-slate-500">Камера / таймлайн / конфигурация exit-zone</div>
            </div>

            <div class="flex-1"></div>

            <select v-model.number="dashCameraId" @change="onDashCameraChange"
              class="rounded-2xl border border-slate-200 px-4 py-2 text-sm">
              <option :value="null">Выберите камеру</option>
              <option v-for="c in cameras" :key="c.camera_id" :value="c.camera_id">Камера {{ c.camera_id }}</option>
            </select>

            <select v-model="dashTrackSel" @change="onDashTrackChange" :disabled="!dashCameraId"
              class="rounded-2xl border border-slate-200 px-4 py-2 text-sm disabled:opacity-40">
              <option value="overall">Общая аналитика</option>
              <option v-for="t in dashTracks" :key="t" :value="String(t)">ID {{ t }}</option>
            </select>

            <button @click="refreshDashboard" :disabled="!dashCameraId"
              class="rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-40">
              Обновить
            </button>

            <button @click="openConfigModal" :disabled="!dashCameraId"
              class="rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-700 transition hover:bg-indigo-100 disabled:opacity-40">
              Настроить выход
            </button>

            <button @click="openClearModal" :disabled="!dashCameraId"
              class="rounded-2xl border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-100 disabled:opacity-40">
              Очистить
            </button>
          </div>
        </div>

        <!-- Overall -->
        <div v-if="dashCameraId && dashTrackSel === 'overall'">
          <div class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div class="rounded-3xl bg-white p-5 shadow-sm">
              <div class="text-sm text-slate-500">Длительность</div>
              <div class="mt-2 text-3xl font-bold">{{ fmtNum(camKpi?.duration_sec, 1) }}</div>
              <div class="mt-1 text-xs text-slate-400">seconds</div>
            </div>
            <div class="rounded-3xl bg-white p-5 shadow-sm">
              <div class="text-sm text-slate-500">Среднее людей</div>
              <div class="mt-2 text-3xl font-bold">{{ fmtNum(camKpi?.avg_people, 2) }}</div>
            </div>
            <div class="rounded-3xl bg-white p-5 shadow-sm">
              <div class="text-sm text-slate-500">Макс людей</div>
              <div class="mt-2 text-3xl font-bold">{{ camKpi?.max_people ?? 0 }}</div>
            </div>
            <div class="rounded-3xl bg-white p-5 shadow-sm">
              <div class="text-sm text-slate-500">Уникальных треков</div>
              <div class="mt-2 text-3xl font-bold">{{ camKpi?.unique_tracks ?? 0 }}</div>
            </div>
          </div>

          <div v-if="camTimeline.length===0" class="mt-5 rounded-3xl bg-white p-8 text-slate-500 shadow-sm">
            Пока нет timeline точек.
          </div>

          <div v-else class="mt-5 space-y-5">
            <div class="rounded-3xl bg-white p-5 shadow-sm">
              <LineChart
                title="Люди и объекты"
                x-label="Время (сек)"
                y-label="Количество"
                :x-values="camTimeline.map(r => Number(r.t_sec))"
                :series="[
                  { name: 'Люди', color: '#2563eb', values: camTimeline.map(r => Number(r.people_total)) },
                  { name: 'Объекты', color: '#f59e0b', values: camTimeline.map(r => Number(r.objects_total)) }
                ]"
              />
            </div>

            <div class="rounded-3xl bg-white p-5 shadow-sm">
              <LineChart
                title="Exit-zone / Carrying"
                x-label="Время (сек)"
                y-label="Количество"
                :x-values="camTimeline.map(r => Number(r.t_sec))"
                :series="[
                  { name: 'В exit-zone', color: '#a855f7', values: camTimeline.map(r => Number(r.people_in_exit_zone)) },
                  { name: 'Несут', color: '#16a34a', values: camTimeline.map(r => Number(r.people_carrying)) }
                ]"
              />
            </div>

            <div class="rounded-3xl bg-white p-5 shadow-sm">
              <div class="text-sm text-slate-500">Конфигурация</div>
              <div class="mt-2 text-sm">
                exit_line: <span class="font-mono">{{ camConfig?.exit_line ? 'set' : 'not set' }}</span>,
                exit_zone: <span class="font-mono">{{ camConfig?.exit_zone ? 'set' : 'not set' }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Track timeline -->
        <div v-else-if="dashCameraId && dashTrackSel !== 'overall'">
          <div class="mt-5 rounded-3xl bg-white p-5 shadow-sm">
            <div class="flex items-center justify-between gap-4">
              <div>
                <div class="text-xl font-bold">Таймлайн состояния</div>
                <div class="text-sm text-slate-500">
                  Камера {{ dashCameraId }} - ID {{ dashTrackSel }}
                </div>
              </div>
              <div class="text-sm text-slate-500">Диапазон: 0 – {{ timelineMaxTrack.toFixed(1) }} сек</div>
            </div>

            <div v-if="dashSegments.length===0" class="mt-4 text-slate-500">
              Нет сегментов для трека. Нажми "Обновить" через пару секунд.
            </div>

            <div v-else class="mt-4">
              <div class="relative h-6 w-full rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
                <div v-for="s in dashSegments" :key="s.id" class="absolute inset-y-0"
                  :title="`${s.state}: ${s.start_sec.toFixed(1)}–${s.end_sec.toFixed(1)}`"
                  :style="segmentStyle(s)">
                </div>
              </div>

              <div class="mt-3 flex flex-wrap gap-3 text-xs text-slate-600">
                <span class="inline-flex items-center gap-2">
                  <span class="h-3 w-3 rounded" style="background:#9ca3af;"></span> normal
                </span>
                <span class="inline-flex items-center gap-2">
                  <span class="h-3 w-3 rounded" style="background:#a855f7;"></span> in_exit_zone
                </span>
                <span class="inline-flex items-center gap-2">
                  <span class="h-3 w-3 rounded" style="background:#16a34a;"></span> carrying
                </span>
                <span class="inline-flex items-center gap-2">
                  <span class="h-3 w-3 rounded" style="background:#0ea5e9;"></span> carrying_in_exit_zone
                </span>
              </div>

              <div class="mt-4 overflow-auto rounded-2xl border border-slate-200">
                <table class="min-w-full text-sm">
                  <thead class="bg-slate-50 text-slate-600">
                    <tr>
                      <th class="px-3 py-2 text-left font-semibold">state</th>
                      <th class="px-3 py-2 text-left font-semibold">start</th>
                      <th class="px-3 py-2 text-left font-semibold">end</th>
                      <th class="px-3 py-2 text-left font-semibold">dur</th>
                    </tr>
                  </thead>
                  <tbody class="bg-white">
                    <tr v-for="s in dashSegments" :key="s.id" class="border-t border-slate-100">
                      <td class="px-3 py-2">{{ s.state }}</td>
                      <td class="px-3 py-2">{{ s.start_sec.toFixed(1) }}</td>
                      <td class="px-3 py-2">{{ s.end_sec.toFixed(1) }}</td>
                      <td class="px-3 py-2">{{ (s.end_sec - s.start_sec).toFixed(1) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

            </div>
          </div>
        </div>

        <div v-else class="mt-5 rounded-3xl bg-white p-8 text-slate-500 shadow-sm">
          Выберите камеру.
        </div>
      </section>
    </main>

    <!-- Viewer modal -->
    <div v-if="viewer.open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" @click.self="closeViewer()">
      <div class="w-full max-w-7xl overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <div class="text-lg font-bold">Камера {{ viewer.camera_id }}</div>
            <div class="text-sm text-slate-500">{{ viewer.status }}</div>
          </div>

          <div class="flex items-center gap-4">
            <label class="flex items-center gap-2 text-sm">
              <input type="checkbox" v-model="viewer.showBoxes" />
              Боксы
            </label>

            <label class="flex items-center gap-2 text-sm" :title="viewer.hasKeypoints ? '' : 'Скелеты доступны только если backend отдаёт keypoints (pose-модель)'" >
              <input type="checkbox" v-model="viewer.showSkeleton" :disabled="!viewer.hasKeypoints" />
              Скелеты
            </label>

            <label class="flex items-center gap-2 text-sm">
              <input type="checkbox" v-model="viewer.showLabels" />
              Метки
            </label>

            <button @click="closeViewer()" class="rounded-xl bg-slate-100 px-4 py-2 text-sm hover:bg-slate-200">
              Закрыть
            </button>
          </div>
        </div>

        <div ref="viewerWrap" class="relative aspect-video bg-black">
          <img ref="viewerImg" :src="streamUrl(viewer.camera_id)" @load="onViewerImgLoad" class="h-full w-full object-contain" />
          <canvas ref="canvas" class="pointer-events-none absolute inset-0 h-full w-full"></canvas>
        </div>
      </div>
    </div>

    <!-- Config modal -->
    <div v-if="configModal.open" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-6" @click.self="closeConfigModal">
      <div class="w-full max-w-5xl overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div class="border-b border-slate-200 px-6 py-4 flex items-center justify-between">
          <div>
            <div class="text-lg font-bold">Настройка выхода (exit-line / exit-zone)</div>
            <div class="text-sm text-slate-500">Камера {{ configModal.cameraId }}. Клики по кадру: линия = 2 точки, зона = многоугольник.</div>
          </div>
          <button @click="closeConfigModal" class="rounded-xl bg-slate-100 px-4 py-2 text-sm hover:bg-slate-200">Закрыть</button>
        </div>

        <div class="p-6">
          <div class="flex flex-wrap gap-3 mb-4">
            <button @click="mode='line'" class="rounded-2xl px-4 py-2 text-sm font-medium"
              :class="mode==='line' ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200'">
              Рисовать линию
            </button>
            <button @click="mode='zone'" class="rounded-2xl px-4 py-2 text-sm font-medium"
              :class="mode==='zone' ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200'">
              Рисовать зону
            </button>
            <button @click="resetDraft" class="rounded-2xl border border-slate-200 px-4 py-2 text-sm hover:bg-slate-100">
              Сброс черновика
            </button>
            <button @click="finishZone" :disabled="mode!=='zone' || draftZone.length<3"
              class="rounded-2xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40">
              Завершить зону
            </button>
            <div class="flex-1"></div>
            <button @click="saveConfig" class="rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
              Сохранить
            </button>
          </div>

          <div ref="cfgWrap" class="relative aspect-video bg-black rounded-2xl overflow-hidden">
            <img ref="cfgImg" :src="annotUrl(configModal.cameraId)" @load="onCfgImgLoad" class="h-full w-full object-contain" />
            <canvas ref="cfgCanvas" class="absolute inset-0 h-full w-full cursor-crosshair" @click="onCfgClick"></canvas>
          </div>

          <div class="mt-4 text-xs text-slate-500 font-mono whitespace-pre-wrap">
            draftLine: {{ JSON.stringify(draftLine) }}
            draftZone: {{ JSON.stringify(draftZone) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Clear modal -->
    <div v-if="clearModal.open" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-6" @click.self="closeClearModal">
      <div class="w-full max-w-md rounded-3xl bg-white shadow-2xl">
        <div class="border-b border-slate-200 px-6 py-4">
          <div class="text-lg font-bold">Подтверждение</div>
        </div>

        <div class="p-6">
          <div class="text-base">
            Очистить аналитику для <span class="font-bold">Камера {{ clearModal.cameraId }}</span>?
          </div>
          <div class="mt-3 text-sm text-slate-500">
            Timeline/segments/events и snapshot-файлы будут удалены.
          </div>

          <div class="mt-6 flex justify-end gap-3">
            <button @click="closeClearModal" class="rounded-2xl bg-slate-100 px-4 py-2 text-sm hover:bg-slate-200">Отмена</button>
            <button @click="confirmClearCamera" class="rounded-2xl bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700">
              Да, очистить
            </button>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref, computed } from "vue";
import { api, API_BASE } from "./api";
import LineChart from "./components/LineChart.vue";

const tab = ref("cameras");
const cameras = ref([]);
const events = ref([]);
const ackFilter = ref("unacked");

// viewer
const viewer = reactive({
  open: false,
  camera_id: null,
  status: "",
  showBoxes: true,
  showSkeleton: false,
  showLabels: true,
  hasKeypoints: false,
});

const viewerWrap = ref(null);
const canvas = ref(null);
const viewerImg = ref(null);

let overlayTimer = null;
let resizeObs = null;

let timers = [];

// dashboard
const dashCameraId = ref(null);
const dashTrackSel = ref("overall");
const dashTracks = ref([]);
const dashSegments = ref([]);
const camKpi = ref(null);
const camTimeline = ref([]);
const camConfig = ref(null);

const clearModal = reactive({ open: false, cameraId: null });

// config modal
const configModal = reactive({ open: false, cameraId: null });
const mode = ref("line");
const cfgWrap = ref(null);
const cfgImg = ref(null);
const cfgCanvas = ref(null);

let cfgCssW = 0, cfgCssH = 0;

const draftLine = ref([]);
const draftZone = ref([]);
const savedZone = ref(null);

// --- helpers ---
function fmtNum(v, digits) {
  const x = Number(v);
  if (!Number.isFinite(x)) return (0).toFixed(digits);
  return x.toFixed(digits);
}

function formatTs(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

// urls
function streamUrl(cameraId) { return `${API_BASE}/api/stream/${cameraId}.mjpg`; }
function annotUrl(cameraId) { return `${API_BASE}/api/stream_annotated/${cameraId}.mjpg`; }

// cameras/events
async function refreshCameras() {
  const r = await api.get("/api/cameras");
  cameras.value = r.data;

  if (viewer.open) {
    const c = cameras.value.find(x => x.camera_id === viewer.camera_id);
    viewer.status = c ? c.status : "";
  }
}

async function refreshEvents() {
  const r = await api.get(`/api/events?limit=200&ack=${ackFilter.value}`);
  events.value = r.data.events || [];
}

async function onUpload(e) {
  const files = Array.from(e.target.files || []);
  if (!files.length) return;

  const fd = new FormData();
  for (const f of files) fd.append("files", f);

  await api.post("/api/cameras/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
  await refreshCameras();
}

async function stopCamera(cameraId) {
  await api.post(`/api/cameras/${cameraId}/stop`);
  await refreshCameras();
}

async function ackEvent(eventId, status) {
  await api.post(`/api/events/${eventId}/ack`, { status, note: "" });
  await refreshEvents();
}

// dashboard
async function onDashCameraChange() {
  dashTracks.value = [];
  dashSegments.value = [];
  camKpi.value = null;
  camTimeline.value = [];
  camConfig.value = null;
  dashTrackSel.value = "overall";

  if (!dashCameraId.value) return;

  const [r, cfg] = await Promise.all([
    api.get(`/api/tracks?camera_id=${dashCameraId.value}`),
    api.get(`/api/camera/${dashCameraId.value}/config`)
  ]);

  dashTracks.value = r.data.tracks || [];
  camConfig.value = cfg.data;

  await loadCameraDashboard();
}

async function onDashTrackChange() {
  dashSegments.value = [];
  if (!dashCameraId.value) return;

  if (dashTrackSel.value === "overall") await loadCameraDashboard();
  else await loadTimeline();
}

async function refreshDashboard() {
  if (!dashCameraId.value) return;
  if (dashTrackSel.value === "overall") await loadCameraDashboard();
  else await loadTimeline();
}

async function loadCameraDashboard() {
  if (!dashCameraId.value) return;

  const [k, t, cfg] = await Promise.all([
    api.get(`/api/camera/kpi?camera_id=${dashCameraId.value}`),
    api.get(`/api/camera/timeline?camera_id=${dashCameraId.value}&limit=2000`),
    api.get(`/api/camera/${dashCameraId.value}/config`)
  ]);

  camKpi.value = k.data.kpi;
  camTimeline.value = t.data.timeline || [];
  camConfig.value = cfg.data;
}

async function loadTimeline() {
  const trackId = parseInt(dashTrackSel.value, 10);
  if (!Number.isFinite(trackId)) return;

  const r = await api.get(`/api/track_timeline?camera_id=${dashCameraId.value}&track_id=${trackId}`);
  dashSegments.value = (r.data.segments || []).map(s => ({
    ...s,
    start_sec: Number(s.start_sec),
    end_sec: Number(s.end_sec),
  }));
}

const timelineMaxTrack = computed(() => {
  if (!dashSegments.value.length) return 0;
  return Math.max(...dashSegments.value.map(s => Number(s.end_sec) || 0));
});

function stateColor(st) {
  if (st === "in_exit_zone") return "#a855f7";
  if (st === "carrying") return "#16a34a";
  if (st === "carrying_in_exit_zone") return "#0ea5e9";
  return "#9ca3af";
}

function segmentStyle(s) {
  const maxT = Math.max(1e-6, timelineMaxTrack.value);
  const leftPct = (s.start_sec / maxT) * 100;
  const widthPct = ((s.end_sec - s.start_sec) / maxT) * 100;
  return { left: `${leftPct}%`, width: `${Math.max(0.2, widthPct)}%`, background: stateColor(s.state), opacity: 0.9 };
}

// viewer overlay
function openViewer(cam) {
  viewer.open = true;
  viewer.camera_id = cam.camera_id;
  viewer.status = cam.status;
  startOverlayLoop();
}

function closeViewer() {
  viewer.open = false;
  viewer.camera_id = null;
  stopOverlayLoop();
  clearCanvas(canvas.value);
}

function onViewerImgLoad() {
  resizeCanvasToWrap(viewerWrap.value, canvas.value);
}

function resizeCanvasToWrap(wrapEl, canvasEl) {
  if (!wrapEl || !canvasEl) return;
  const rect = wrapEl.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvasEl.width = Math.max(1, Math.floor(rect.width * dpr));
  canvasEl.height = Math.max(1, Math.floor(rect.height * dpr));
  const ctx = canvasEl.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  canvasEl._cssW = rect.width;
  canvasEl._cssH = rect.height;
}

function clearCanvas(c) {
  if (!c) return;
  const ctx = c.getContext("2d");
  const cssW = c._cssW || 0;
  const cssH = c._cssH || 0;
  ctx.clearRect(0, 0, cssW, cssH);
}

function getContainedRect(imgEl, cssW, cssH) {
  if (!imgEl || !imgEl.naturalWidth || !imgEl.naturalHeight) return { x: 0, y: 0, w: cssW, h: cssH };
  const iw = imgEl.naturalWidth, ih = imgEl.naturalHeight;
  const scale = Math.min(cssW / iw, cssH / ih);
  const dw = iw * scale, dh = ih * scale;
  return { x: (cssW - dw) / 2, y: (cssH - dh) / 2, w: dw, h: dh };
}

function detColor(ent, d) {
  if (ent === "object") return "#f59e0b";
  if (d.carrying && d.in_exit_zone) return "#0ea5e9";
  if (d.carrying) return "#16a34a";
  if (d.in_exit_zone) return "#a855f7";
  return "#22c55e";
}

function drawOverlay(overlay) {
  const c = canvas.value;
  if (!c) return;
  const ctx = c.getContext("2d");
  const cssW = c._cssW || 0, cssH = c._cssH || 0;
  ctx.clearRect(0, 0, cssW, cssH);

  const imgRect = getContainedRect(viewerImg.value, cssW, cssH);
  const W = imgRect.w, H = imgRect.h, offX = imgRect.x, offY = imgRect.y;

  // draw exit configs
  const cfg = overlay?.config || {};
  const exitLine = cfg.exit_line;
  const exitZone = cfg.exit_zone;

  if (exitZone && exitZone.length >= 3) {
    ctx.strokeStyle = "#ff00ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    exitZone.forEach((p, i) => {
      const x = offX + Number(p[0]) * W;
      const y = offY + Number(p[1]) * H;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();
  }

  if (exitLine && exitLine.length === 2) {
    ctx.strokeStyle = "#ff00ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(offX + exitLine[0][0] * W, offY + exitLine[0][1] * H);
    ctx.lineTo(offX + exitLine[1][0] * W, offY + exitLine[1][1] * H);
    ctx.stroke();
  }

  const dets = overlay?.detections || [];
  viewer.hasKeypoints = dets.some(d => Array.isArray(d.keypoints) && d.keypoints.length >= 17);

  for (const d of dets) {
    const ent = d.entity || "person";
    const color = detColor(ent, d);
    const [x1n, y1n, x2n, y2n] = d.bbox || [0, 0, 0, 0];
    const x = offX + x1n * W;
    const y = offY + y1n * H;
    const bw = (x2n - x1n) * W;
    const bh = (y2n - y1n) * H;

    if (viewer.showBoxes) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, bw, bh);
    }

    if (viewer.showLabels) {
      ctx.fillStyle = color;
      ctx.font = "13px sans-serif";
      const label = ent === "object"
        ? `${d.cls_name || "obj"} T${d.track_id}`
        : `ID:${d.track_id}${d.carrying ? " carrying" : ""}${d.in_exit_zone ? " exit" : ""}`;
      ctx.fillText(label, x + 3, Math.max(13, y - 5));
    }

    // skeleton (если когда-нибудь появятся keypoints)
    if (viewer.showSkeleton && Array.isArray(d.keypoints) && d.keypoints.length >= 17) {
      // здесь можно будет добавить отрисовку, но сейчас backend keypoints не отдаёт
    }
  }
}

async function overlayTick() {
  if (!viewer.open || viewer.camera_id == null) return;
  const r = await api.get(`/api/overlay/${viewer.camera_id}`);
  drawOverlay(r.data);
}

function startOverlayLoop() {
  stopOverlayLoop();
  resizeCanvasToWrap(viewerWrap.value, canvas.value);
  overlayTick();

  overlayTimer = setInterval(overlayTick, 150);

  resizeObs = new ResizeObserver(() => resizeCanvasToWrap(viewerWrap.value, canvas.value));
  if (viewerWrap.value) resizeObs.observe(viewerWrap.value);
}

function stopOverlayLoop() {
  if (overlayTimer) clearInterval(overlayTimer);
  overlayTimer = null;
  if (resizeObs) resizeObs.disconnect();
  resizeObs = null;
}

// clear modal
function openClearModal() {
  if (!dashCameraId.value) return;
  clearModal.open = true;
  clearModal.cameraId = dashCameraId.value;
}
function closeClearModal() {
  clearModal.open = false;
  clearModal.cameraId = null;
}
async function confirmClearCamera() {
  await api.post(`/api/camera/${clearModal.cameraId}/clear`);
  await onDashCameraChange();
  closeClearModal();
}

// SSE events (best effort)
let evSource = null;
function startSse() {
  try {
    evSource = new EventSource(`${API_BASE}/api/events/stream`);
    evSource.addEventListener("event", (msg) => {
      const ev = JSON.parse(msg.data);
      events.value = [ev, ...events.value].slice(0, 200);
    });
  } catch (e) {}
}
function stopSse() {
  if (evSource) evSource.close();
  evSource = null;
}

// ---- Config modal ----
function openConfigModal() {
  if (!dashCameraId.value) return;
  configModal.open = true;
  configModal.cameraId = dashCameraId.value;
  resetDraft();

  if (camConfig.value?.exit_line) draftLine.value = JSON.parse(JSON.stringify(camConfig.value.exit_line));
  if (camConfig.value?.exit_zone) {
    savedZone.value = JSON.parse(JSON.stringify(camConfig.value.exit_zone));
    draftZone.value = JSON.parse(JSON.stringify(camConfig.value.exit_zone));
  }
  setTimeout(() => resizeCfgCanvas(), 50);
}

function closeConfigModal() {
  configModal.open = false;
  configModal.cameraId = null;
}

function onCfgImgLoad() { resizeCfgCanvas(); drawCfg(); }

function resizeCfgCanvas() {
  const wrap = cfgWrap.value;
  const c = cfgCanvas.value;
  if (!wrap || !c) return;
  const rect = wrap.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  cfgCssW = rect.width;
  cfgCssH = rect.height;
  c.width = Math.max(1, Math.floor(rect.width * dpr));
  c.height = Math.max(1, Math.floor(rect.height * dpr));
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawCfg();
}

function getCfgContainedRect() {
  return getContainedRect(cfgImg.value, cfgCssW, cfgCssH);
}

function toNormFromClick(ev) {
  const c = cfgCanvas.value;
  if (!c) return null;
  const rect = c.getBoundingClientRect();
  const xCss = ev.clientX - rect.left;
  const yCss = ev.clientY - rect.top;

  const imgRect = getCfgContainedRect();
  const x = (xCss - imgRect.x) / Math.max(1e-6, imgRect.w);
  const y = (yCss - imgRect.y) / Math.max(1e-6, imgRect.h);

  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return [Number(x), Number(y)];
}

function onCfgClick(ev) {
  const p = toNormFromClick(ev);
  if (!p) return;

  if (mode.value === "line") {
    if (draftLine.value.length >= 2) draftLine.value = [];
    draftLine.value.push(p);
  } else {
    draftZone.value.push(p);
  }
  drawCfg();
}

function finishZone() {
  if (draftZone.value.length >= 3) savedZone.value = JSON.parse(JSON.stringify(draftZone.value));
  drawCfg();
}

function resetDraft() {
  draftLine.value = [];
  draftZone.value = [];
  savedZone.value = null;
  drawCfg();
}

function drawCfg() {
  const c = cfgCanvas.value;
  if (!c) return;
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, cfgCssW, cfgCssH);

  const imgRect = getCfgContainedRect();
  const W = imgRect.w, H = imgRect.h, offX = imgRect.x, offY = imgRect.y;

  // zone
  const z = savedZone.value || draftZone.value;
  if (z && z.length >= 2) {
    ctx.strokeStyle = "#ff00ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    z.forEach((p, i) => {
      const x = offX + p[0] * W;
      const y = offY + p[1] * H;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    if (z.length >= 3) ctx.closePath();
    ctx.stroke();
  }

  // line points + line
  if (draftLine.value.length >= 1) {
    ctx.fillStyle = "#ff00ff";
    for (const p of draftLine.value) {
      ctx.beginPath();
      ctx.arc(offX + p[0]*W, offY + p[1]*H, 4, 0, Math.PI*2);
      ctx.fill();
    }
  }
  if (draftLine.value.length === 2) {
    ctx.strokeStyle = "#ff00ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(offX + draftLine.value[0][0]*W, offY + draftLine.value[0][1]*H);
    ctx.lineTo(offX + draftLine.value[1][0]*W, offY + draftLine.value[1][1]*H);
    ctx.stroke();
  }
}

async function saveConfig() {
  if (!configModal.cameraId) return;
  const exit_line = (draftLine.value.length === 2) ? draftLine.value : (camConfig.value?.exit_line || null);
  const exit_zone = (savedZone.value && savedZone.value.length >= 3) ? savedZone.value : (camConfig.value?.exit_zone || null);

  const r = await api.post(`/api/camera/${configModal.cameraId}/config`, { exit_line, exit_zone });
  camConfig.value = r.data.config;
  closeConfigModal();
}

// lifecycle
onMounted(async () => {
  await refreshCameras();
  await refreshEvents();

  timers.push(setInterval(refreshCameras, 1500));
  timers.push(setInterval(refreshEvents, 2500));

  startSse();
});

onBeforeUnmount(() => {
  for (const t of timers) clearInterval(t);
  stopOverlayLoop();
  stopSse();
});
</script>