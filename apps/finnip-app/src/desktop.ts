// Desktop overlay (the macOS app loads this page with ?desktop=1 in a transparent, click-through window):
// which scene the window shows, from the conversation state and the panels on screen.
export type Scene = "hidden" | "corner" | "center";

/** panel: the server stats or the agenda is on screen (they take the center over a dimmed desktop). */
export function sceneFor(state: string, panel: boolean): Scene {
  if (panel) return "center";
  return state === "listening" || state === "thinking" || state === "speaking" ? "corner" : "hidden";
}

type Playing = { active: boolean; state: string; title: string | null; artist: string | null };

/** The music notice comes up when a new song starts, never again for the same song or on pause. */
export class MusicNotice {
  private last = "";
  shouldShow(np: Playing): boolean {
    if (!np.active || np.state !== "playing") return false;
    const key = `${np.title}|${np.artist}`;
    if (key === this.last) return false;
    this.last = key;
    return true;
  }
}
