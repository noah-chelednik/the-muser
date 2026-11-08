/** Several Deck instances can be mounted (skin dock and the Beats sheet). Only the newest one owns
 * the computer keyboard and MIDI, so a key never plays twice. */
const stack: number[] = []
let n = 0
export function claimDeck(): { id: number; release: () => void } {
  const id = ++n
  stack.push(id)
  return { id, release: () => { const i = stack.indexOf(id); if (i >= 0) stack.splice(i, 1) } }
}
export const ownsInput = (id: number) => stack[stack.length - 1] === id
