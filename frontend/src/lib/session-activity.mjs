// Only trusted, visible interactions count. Timers/polling never call activity.
export function shouldSignalActivity(event, visible, now, lastSent) {
  return event.isTrusted === true && visible && now-lastSent >= 60000 &&
    ["pointerdown","keydown","input","wheel","touchstart"].includes(event.type);
}
