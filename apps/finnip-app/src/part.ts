// A 3D part as a hologram on the desktop overlay: the STL (served by the gateway) drawn full screen as
// glowing edges over a faint fresnel surface, in the monitors' color with the same bloom as the core, so
// zooming in never cuts it. It is turned by hand gestures (hands.ts), by voice ("vista de arriba",
// resolved by the gateway into part_view) or with the mouse inside a central square: the macOS app takes
// the cursor only there (see onBox), clicks elsewhere still reach the apps underneath. Drawn while open.
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { clampZoom, dragPose, PART_START, partPose, type PartPose } from "./desktop";
import { glowAlpha } from "./holo";

export type PartInfo = { slug: string; version: number; name: string; size_mm: number[] | null; url: string };

const additive = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false };
const SURFACE_VERT = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }`;
const SURFACE_FRAG = /* glsl */ `
  uniform vec3 uColor;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float rim = pow(1.0 - abs(dot(normalize(vNormal), normalize(vView))), 2.0);
    gl_FragColor = vec4(uColor, 0.05 + 0.45 * rim); // faint faces, brighter silhouette
  }`;
const FPS_MS = 33;

export class PartView {
  open = false;
  private renderer: THREE.WebGLRenderer;
  private composer: EffectComposer;
  private bloom: UnrealBloomPass;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(32, 1, 0.1, 5000);
  private pivot = new THREE.Group(); // turned by the pose
  private model = new THREE.Group(); // the STL, Z up as printed -> Y up
  private color = new THREE.Color(0x38e1ff);
  private edges = new THREE.LineBasicMaterial({ color: this.color, opacity: 0.95, ...additive });
  private surface = new THREE.ShaderMaterial({
    uniforms: { uColor: { value: this.color } }, vertexShader: SURFACE_VERT, fragmentShader: SURFACE_FRAG,
    side: THREE.DoubleSide, ...additive,
  });
  private pose: PartPose = { ...PART_START };
  private shown = { ...PART_START }; // eased toward pose
  private fit = 1; // camera distance that frames the part at zoom 1
  private drag: { x: number; y: number } | null = null;
  private last = 0;
  private token = 0; // a newer open() wins over a slower earlier load

  constructor(
    private box: HTMLElement, // full screen, holds the canvas
    private hit: HTMLElement, // central square that takes the mouse
    private label: HTMLElement,
    private onBox: (open: boolean, rect: [number, number, number, number] | null) => void,
  ) {
    const canvas = box.querySelector("canvas")!;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); // full screen: Retina would cost too much GPU
    this.renderer.setClearColor(0x000000, 0);
    this.model.rotation.x = -Math.PI / 2;
    this.pivot.add(this.model);
    this.scene.add(this.pivot);
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.6, 0.4, 0.05);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this.composer.addPass(new ShaderPass(glowAlpha(false))); // light on black -> see-through overlay

    hit.addEventListener("pointerdown", (e) => {
      if ((e.target as HTMLElement).closest("button")) return;
      this.drag = { x: e.clientX, y: e.clientY };
      hit.setPointerCapture(e.pointerId);
    });
    hit.addEventListener("pointermove", (e) => {
      if (!this.drag) return;
      this.pose = dragPose(this.pose, e.clientX - this.drag.x, e.clientY - this.drag.y);
      this.drag = { x: e.clientX, y: e.clientY };
    });
    hit.addEventListener("pointerup", () => (this.drag = null));
    hit.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.pose = { ...this.pose, zoom: clampZoom(this.pose.zoom * Math.exp(-e.deltaY * 0.002)) };
    }, { passive: false });
    hit.querySelector("button")?.addEventListener("click", () => this.close());
    addEventListener("resize", () => this.open && this.layout());
  }

  setColor(color: THREE.Color) {
    this.color.copy(color);
  }

  async show(part: PartInfo) {
    const token = ++this.token;
    const geometry = await new STLLoader().loadAsync(part.url);
    if (token !== this.token) return geometry.dispose();
    this.clear();
    geometry.computeVertexNormals();
    geometry.center();
    geometry.computeBoundingSphere();
    this.model.add(new THREE.Mesh(geometry, this.surface), new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 25), this.edges));
    const radius = geometry.boundingSphere?.radius || 1;
    this.fit = radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2)) * 1.1;
    this.pose = { ...PART_START };
    this.shown = { ...PART_START };
    const size = part.size_mm?.map((v) => Math.round(v * 10) / 10).join(" × ");
    this.label.textContent = `${part.name} · v${part.version}${size ? ` · ${size} mm` : ""}`;
    this.box.hidden = false;
    this.open = true;
    this.layout();
    requestAnimationFrame((t) => this.frame(t));
  }

  /** Hand gestures (hands.ts): turn by a fraction of the camera image, zoom by a factor. */
  rotateBy(dx: number, dy: number) {
    const r = this.hit.getBoundingClientRect();
    this.pose = dragPose(this.pose, dx * r.width * 1.5, dy * r.height * 1.5);
  }

  zoomBy(factor: number) {
    this.pose = { ...this.pose, zoom: clampZoom(this.pose.zoom * factor) };
  }

  /** Shows in the label whether the hands are being followed, or why the camera could not start. */
  setHands(on: boolean, error?: string) {
    this.box.classList.toggle("hands-on", on);
    this.box.dataset.handsError = error ? `sin manos: ${error}` : "";
  }

  view(view: string) {
    if (!this.open) return;
    if (view === "close") return this.close();
    this.pose = partPose(this.pose, view);
  }

  close() {
    if (!this.open) return;
    this.open = false;
    this.token++;
    this.box.hidden = true;
    this.clear();
    this.onBox(false, null);
  }

  private clear() {
    for (const child of [...this.model.children]) {
      (child as THREE.Mesh).geometry.dispose();
      this.model.remove(child);
    }
  }

  private layout() {
    const [w, h] = [innerWidth, innerHeight];
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.setSize(w / 2, h / 2);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    const r = this.hit.getBoundingClientRect();
    this.onBox(true, [r.left, r.top, r.width, r.height]);
  }

  private frame(now: number) {
    if (!this.open) return;
    requestAnimationFrame((t) => this.frame(t));
    if (now - this.last < FPS_MS) return;
    const dt = Math.min((now - (this.last || now)) / 1000, 0.1);
    this.last = now;
    if (this.pose.spin) this.pose = { ...this.pose, yaw: this.pose.yaw + dt * 0.6 };
    const ease = 1 - Math.exp(-dt * 8);
    for (const key of ["pitch", "yaw", "zoom"] as const) this.shown[key] += (this.pose[key] - this.shown[key]) * ease;
    this.pivot.rotation.set(this.shown.pitch, this.shown.yaw, 0, "XYZ");
    this.camera.position.set(0, 0, this.fit / this.shown.zoom);
    this.camera.lookAt(0, 0, 0);
    this.composer.render();
  }
}
