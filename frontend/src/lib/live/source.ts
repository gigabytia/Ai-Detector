import { parsePacket, type PreviewMetadata } from './protocol'

export interface PreviewFrame {
  image: ImageBitmap
  metadata: PreviewMetadata
}
export type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'stopped'
export interface CameraImageSource {
  start(): void
  stop(): void
}

/** One decoding job + latest pending packet, bounded memory even on slow devices. */
export class WsPreviewSource implements CameraImageSource {
  private socket: WebSocket | null = null
  private timer: ReturnType<typeof setTimeout> | undefined
  private stopped = true
  private generation = 0
  private retry = 500
  private pending: ArrayBuffer | null = null
  private decoding = false

  constructor(
    private cameraId: string,
    private onFrame: (frame: PreviewFrame) => void,
    private onState: (state: ConnectionState) => void,
  ) {}

  start() {
    if (!this.stopped) return
    this.stopped = false
    this.generation++
    this.connect()
  }
  stop() {
    this.stopped = true
    this.generation++
    clearTimeout(this.timer)
    this.pending = null
    this.socket?.close()
    this.socket = null
    this.onState('stopped')
  }
  private connect() {
    if (this.stopped) return
    this.onState(this.retry === 500 ? 'connecting' : 'reconnecting')
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(
      `${scheme}//${location.host}/live/cameras/${encodeURIComponent(this.cameraId)}/preview`,
    )
    this.socket = socket
    socket.binaryType = 'arraybuffer'
    socket.onmessage = (event: MessageEvent<unknown>) => {
      if (this.stopped || this.socket !== socket || !(event.data instanceof ArrayBuffer)) return
      this.pending = event.data
      void this.decode()
    }
    socket.onerror = () => socket.close()
    socket.onclose = () => {
      if (this.stopped || this.socket !== socket) return
      this.onState('reconnecting')
      this.timer = setTimeout(() => this.connect(), this.retry)
      this.retry = Math.min(this.retry * 2, 8000)
    }
  }
  private async decode() {
    if (this.decoding) return
    this.decoding = true
    try {
      while (this.pending && !this.stopped) {
        const data = this.pending
        this.pending = null
        const generation = this.generation
        try {
          const { metadata, jpeg } = parsePacket(data, this.cameraId)
          const image = await createImageBitmap(jpeg)
          if (this.stopped || generation !== this.generation) {
            image.close()
            continue
          }
          this.retry = 500
          this.onState('live')
          this.onFrame({ image, metadata })
        } catch {
          if (!this.stopped && generation === this.generation) this.onState('reconnecting')
        }
      }
    } finally {
      this.decoding = false
    }
  }
}
