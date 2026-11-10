// Holographic core (Three.js + bloom): particle sphere, wire core, HUD rings. Colored like the monitors.
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";

export type HoloState = "off" | "listening" | "thinking" | "speaking";

const BG = 0x020409;
const additive = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false };
// Desktop overlay: the hologram is light on black, so each pixel's brightness becomes its opacity
// (premultiplied): black is see-through and the glow adds onto the Mac's desktop. Bloom keeps no alpha.
const GLOW_ALPHA = {
  uniforms: { tDiffuse: { value: null } },
  vertexShader: "varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
  fragmentShader:
    "uniform sampler2D tDiffuse; varying vec2 vUv; void main() {" +
    " vec4 c = texture2D(tDiffuse, vUv); float m = max(c.r, max(c.g, c.b));" +
    // sRGB output lifts the bloom's faint haze; it must stay invisible, and the box must fade out round.
    " float a = smoothstep(0.07, 0.55, m) * smoothstep(0.5, 0.4, distance(vUv, vec2(0.5)));" +
    " gl_FragColor = vec4(c.rgb * min(1.0, a / max(m, 1e-4)), a); }", // only ever dims, never brightens
};
const BOX = 1.7; // desktop canvas side, relative to the anchor: room for the rings' glow

function arcs(radius: number, spans: [number, number][], seg = 96) {
  const pts: number[] = [];
  for (const [a0, a1] of spans) {
    const n = Math.max(2, Math.round((seg * (a1 - a0)) / (Math.PI * 2)));
    for (let i = 0; i < n; i++) {
      const a = a0 + ((a1 - a0) * i) / n;
      const b = a0 + ((a1 - a0) * (i + 1)) / n;
      pts.push(Math.cos(a) * radius, Math.sin(a) * radius, 0, Math.cos(b) * radius, Math.sin(b) * radius, 0);
    }
  }
  return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
}

function ticks(radius: number, count: number) {
  const pts: number[] = [];
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2;
    const len = i % 6 === 0 ? 0.09 : 0.035;
    pts.push(Math.cos(a) * radius, Math.sin(a) * radius, 0, Math.cos(a) * (radius + len), Math.sin(a) * (radius + len), 0);
  }
  return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
}

function sphere(count: number) {
  const pos = new Float32Array(count * 3);
  const rand = new Float32Array(count);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    pos.set([Math.cos(golden * i) * r, y, Math.sin(golden * i) * r], i * 3);
    rand[i] = Math.random();
  }
  return new THREE.BufferGeometry()
    .setAttribute("position", new THREE.BufferAttribute(pos, 3))
    .setAttribute("aRand", new THREE.BufferAttribute(rand, 1));
}

const VERT = /* glsl */ `
  uniform float uTime, uLevel, uSize, uSpread;
  attribute float aRand;
  varying float vAlpha;
  void main() {
    vec3 p = position;
    float n = sin(p.x * 4.0 + uTime * 1.3) * sin(p.y * 4.0 + uTime * 1.1) * sin(p.z * 4.0 + uTime * 0.9);
    p *= 1.0 + n * (0.03 + uLevel * 0.32) + uLevel * 0.06 + uSpread * aRand;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    // Min 3px: sub-pixel points shimmer (twinkle) as the sphere turns, since there is no AA and 1x pixels.
    gl_PointSize = max(uSize * (0.5 + aRand) / -mv.z, 3.0);
    gl_Position = projectionMatrix * mv;
    // Back half faded: there front and back points overlap and their additive glow sparkles.
    float facing = (normalMatrix * normalize(position)).z;
    vAlpha = (0.12 + 0.5 * aRand) * mix(0.12, 1.0, smoothstep(-0.2, 0.3, facing));
  }`;
const FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    gl_FragColor = vec4(uColor, vAlpha * uOpacity * smoothstep(0.5, 0.05, d));
  }`;

export class Holo {
  private renderer: THREE.WebGLRenderer;
  private composer: EffectComposer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  private root = new THREE.Group(); // placed over the stage
  private core = new THREE.Group(); // scales with the stats HUD
  private globe = new THREE.Group(); // spins in 3D; the flat HUD rings stay facing the camera
  private color = new THREE.Color(0x38e1ff);
  private target = new THREE.Color(0x38e1ff);
  private points: THREE.ShaderMaterial;
  private lineMats: THREE.LineBasicMaterial[] = [];
  private rings: THREE.Object3D[] = [];
  private scanner: THREE.LineSegments;
  private wire: THREE.LineSegments;
  private level = 0;
  private energy = 0.3;
  private spin = 0;
  private scale = 1;
  private clock = new THREE.Clock();
  private bloom: UnrealBloomPass;
  private lastRender = 0;
  state: HoloState = "off";
  shrink = false; // true while the stats HUD is on screen
  paused = false; // desktop overlay: nothing on screen, nothing drawn

  constructor(private canvas: HTMLCanvasElement, private anchor: HTMLElement, private transparent = false) {
    // GPU budget (measured by the user: 60% GPU on an M5 before this): no MSAA (the composer renders to
    // its own targets anyway), 1x pixels (the glow hides it), bloom at half resolution, throttled loop.
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "low-power", alpha: transparent });
    // The overlay's box is small, so it can afford native pixels (Retina on the iPad): at 1x its thin
    // rings and dots came out jagged and blurry.
    this.renderer.setPixelRatio(transparent ? Math.min(devicePixelRatio, 2) : 1);
    // Desktop overlay: no background, the Mac's desktop shows through around the hologram.
    if (transparent) this.renderer.setClearColor(0x000000, 0);
    else this.scene.background = new THREE.Color(BG);
    this.camera.position.z = 6;
    this.scene.add(this.root);
    this.root.add(this.core);
    this.core.add(this.globe);

    this.points = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 }, uLevel: { value: 0 }, uSize: { value: 26 * this.renderer.getPixelRatio() },
        uSpread: { value: 0 }, uColor: { value: this.color }, uOpacity: { value: 1 },
      },
      vertexShader: VERT,
      fragmentShader: FRAG,
      ...additive,
    });
    // Point size does not shrink with the sphere: on the small overlay 2200 points overlapped into a
    // solid ball with spiral moiré, so it gets fewer of them.
    this.globe.add(new THREE.Points(sphere(transparent ? 700 : 2200), this.points));

    const line = (opacity: number) => {
      const m = new THREE.LineBasicMaterial({ color: this.color, opacity, ...additive });
      m.userData.base = opacity;
      this.lineMats.push(m);
      return m;
    };
    this.wire = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(0.42, 1)), line(0.55));
    this.globe.add(this.wire);

    const ringA = new THREE.LineSegments(arcs(1.3, [[0, 1.9], [2.2, 3.3], [3.6, 5.9]]), line(0.7));
    ringA.rotation.x = 1.15;
    const ringB = new THREE.LineSegments(arcs(1.42, [[0.4, 2.6], [3.1, 4.0], [4.4, 6.0]]), line(0.45));
    ringB.rotation.set(1.9, 0.5, 0);
    const tickRing = new THREE.LineSegments(ticks(1.62, 120), line(0.5));
    const outer = new THREE.LineSegments(arcs(1.86, [[0.2, 1.3], [1.6, 1.75], [2.1, 3.0], [3.4, 4.9], [5.2, 5.4]]), line(0.6));
    this.rings = [ringA, ringB, tickRing, outer];
    this.globe.add(ringA, ringB);
    this.core.add(tickRing, outer);
    this.scanner = new THREE.LineSegments(arcs(1.74, [[0, 0.9]]), line(0.95));
    this.core.add(this.scanner);


    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.85, 0.45, 0.08);
    this.composer.addPass(this.bloom);
    if (transparent) Object.assign(this.bloom, { strength: 0.75, radius: 0.4 }); // softer than the app, but its 700 points need it
    this.composer.addPass(new OutputPass());
    if (transparent) this.composer.addPass(new ShaderPass(GLOW_ALPHA));

    new ResizeObserver(() => this.resize()).observe(anchor);
    addEventListener("resize", () => this.resize());
    this.resize();
  }

  /** Monitor color as is; only very dark colors are lifted so the hologram still glows. */
  setColor(rgb: [number, number, number]) {
    const c = new THREE.Color().setRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, THREE.SRGBColorSpace);
    // HSL in sRGB, like the LED's own numbers; in linear space lifting lightness tinted blue violet.
    const hsl = { h: 0, s: 0, l: 0 };
    c.getHSL(hsl, THREE.SRGBColorSpace);
    this.target.setHSL(hsl.h, hsl.s, Math.max(hsl.l, 0.45), THREE.SRGBColorSpace);
  }

  private resize() {
    if (this.transparent) return this.resizeBox();
    const w = innerWidth;
    const h = innerHeight;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.setSize(w / 2, h / 2); // composer.setSize resets it to full size
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    // Center the hologram on the anchor element and size it to fit inside.
    const r = this.anchor.getBoundingClientRect();
    const viewH = 2 * this.camera.position.z * Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    const perPx = viewH / h;
    this.root.position.set((r.left + r.width / 2 - w / 2) * perPx, -(r.top + r.height / 2 - h / 2) * perPx, 0);
    this.scale = (Math.min(r.width, r.height) * 0.46 * perPx) / 1.95;
  }

  /** Desktop overlay: the canvas is only a square around the anchor, with the hologram on the camera's
   *  axis (at a screen corner a full-screen perspective camera stretched it), and far fewer pixels. */
  private resizeBox() {
    const r = this.anchor.getBoundingClientRect();
    const side = Math.round(Math.max(r.width, r.height) * BOX);
    Object.assign(this.canvas.style, {
      left: `${Math.round(r.left + r.width / 2 - side / 2)}px`,
      top: `${Math.round(r.top + r.height / 2 - side / 2)}px`,
      width: `${side}px`,
      height: `${side}px`,
    });
    this.renderer.setSize(side, side, false);
    this.composer.setSize(side, side);
    this.bloom.setSize(side / 2, side / 2);
    this.camera.aspect = 1;
    this.camera.updateProjectionMatrix();
    const viewH = 2 * this.camera.position.z * Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    this.root.position.set(0, 0, 0);
    this.scale = (Math.min(r.width, r.height) * 0.46 * (viewH / side)) / 1.95;
  }

  /** Call every frame with the voice level (0-1) of whoever is talking. */
  frame(level: number) {
    if (this.paused) return;
    // ponytail: fixed per-state frame caps; drop to on-demand rendering if idle still costs too much.
    const now = performance.now();
    const idle = this.state === "off";
    const cap = idle ? 50 : 33; // ~20 fps idle, ~30 fps active (listening, thinking, speaking)
    if (now - this.lastRender < cap) return; // ProMotion runs rAF at 120
    this.lastRender = now;
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const t = this.clock.elapsedTime;
    const s = this.state;
    this.level += (level - this.level) * 0.25;
    const energyTarget = s === "off" ? 0.28 : s === "thinking" ? 0.85 : 0.75 + this.level * 0.25;
    this.energy += (energyTarget - this.energy) * 0.06;
    this.spin += dt * (s === "thinking" ? 2.6 : s === "off" ? 0.12 : 0.4 + this.level * 1.5);

    this.color.lerp(this.target, 0.05);
    this.points.uniforms.uTime.value = t;
    this.points.uniforms.uLevel.value = this.level;
    this.points.uniforms.uOpacity.value = this.energy;
    this.points.uniforms.uSpread.value = s === "thinking" ? 0.06 + Math.sin(t * 6) * 0.03 : 0;
    for (const m of this.lineMats) {
      m.color.copy(this.color); // materials copy the color, they do not share it
      m.opacity = m.userData.base * this.energy;
    }

    const target = this.scale * (this.shrink ? 0.58 : 1) * (1 + this.level * 0.08);
    this.core.scale.setScalar(this.core.scale.x + (target - this.core.scale.x) * 0.08);
    this.globe.rotation.y = this.spin * 0.3;
    this.wire.rotation.set(t * 0.4, this.spin, 0);
    this.rings[0].rotation.z = this.spin * 0.8;
    this.rings[1].rotation.z = -this.spin * 0.55;
    this.rings[2].rotation.z = -this.spin * 0.15;
    this.rings[3].rotation.z = this.spin * 0.25;
    this.scanner.rotation.z = -t * (s === "thinking" ? 5 : 1.2);
    this.scanner.visible = s !== "off";
    this.composer.render();
  }
}
