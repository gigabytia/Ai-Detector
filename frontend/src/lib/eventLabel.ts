export function eventLabel(type: string): string {
  return type === 'PERSON_CROSSED_LINE'
    ? 'lines.crossed'
    : type === 'PERSON_LOITERING_IN_DANGER_ZONE'
      ? 'events.loitering'
      : 'events.entered'
}
