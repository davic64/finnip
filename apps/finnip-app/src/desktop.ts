// Desktop overlay (the macOS app loads this page with ?desktop=1 in a transparent, click-through window):
// which scene the window shows, from the conversation state and the panels on screen.
export type Scene = "hidden" | "corner" | "center" | "part";

/** panel: the server stats or the agenda is on screen (they take the center over a dimmed desktop).
 *  part: a 3D part is open; it takes the center until it is closed. */
export function sceneFor(state: string, panel: boolean, part = false): Scene {
  if (part) return "part";
  if (panel) return "center";
  return state === "listening" || state === "thinking" || state === "speaking" ? "corner" : "hidden";
}

/** How the open 3D part is turned: pitch and yaw in radians, zoom 1 = fit to its box, spin on its own. */
export type PartPose = { pitch: number; yaw: number; zoom: number; spin: boolean };
export const PART_START: PartPose = { pitch: 0.45, yaw: -0.6, zoom: 1, spin: false };
const PITCH_LIMIT = Math.PI / 2;
const VIEWS: Record<string, [number, number]> = {
  top: [PITCH_LIMIT, 0], bottom: [-PITCH_LIMIT, 0], front: [0, 0], back: [0, Math.PI], side: [0, -Math.PI / 2],
};

/** The pose after a spoken order ("top", "spin", "closer"...); "close" is handled by the viewer. */
export function partPose(pose: PartPose, view: string): PartPose {
  if (view in VIEWS) return { ...pose, pitch: VIEWS[view][0], yaw: VIEWS[view][1], spin: false };
  if (view === "reset") return { ...PART_START };
  if (view === "spin") return { ...pose, spin: true };
  if (view === "still") return { ...pose, spin: false };
  if (view === "closer") return { ...pose, zoom: clampZoom(pose.zoom * 1.4) };
  if (view === "farther") return { ...pose, zoom: clampZoom(pose.zoom / 1.4) };
  return pose;
}

/** Mouse drag in CSS pixels turns the part; the pitch stops at straight above or below. */
export function dragPose(pose: PartPose, dx: number, dy: number): PartPose {
  const pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pose.pitch + dy * 0.01));
  return { ...pose, pitch, yaw: pose.yaw + dx * 0.01, spin: false };
}

export const clampZoom = (zoom: number) => Math.max(0.4, Math.min(4, zoom));

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
