import type { Point } from '@/api/zones'
// Coordinates belong to the source image, never the letterboxed viewport.
export function imagePoint(
  x: number,
  y: number,
  width: number,
  height: number,
  imageWidth: number,
  imageHeight: number,
): Point | null {
  if (
    ![x, y, width, height, imageWidth, imageHeight].every(Number.isFinite) ||
    Math.min(width, height, imageWidth, imageHeight) <= 0
  )
    return null
  const scale = Math.min(width / imageWidth, height / imageHeight)
  const px = (x - (width - imageWidth * scale) / 2) / (imageWidth * scale)
  const py = (y - (height - imageHeight * scale) / 2) / (imageHeight * scale)
  return px < 0 || px > 1 || py < 0 || py > 1 ? null : { x: px, y: py }
}
