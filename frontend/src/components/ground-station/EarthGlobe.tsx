/** 3D Earth + orbit visualization — ported from the legacy app's
 * `earth.js` (three.js). Renders the globe, plots the satellite at its
 * live lat/lon/alt (or a simulated orbit when GPS data isn't present yet),
 * and lets the viewer drag to rotate — same interaction the legacy module
 * had. Textures load from the same public CDN the legacy app used; if that
 * fails (offline dev), falls back to a plain lit sphere so the feature
 * still works, just without the photo-realistic texture. */
import { useEffect, useRef } from "react";
import * as THREE from "three";

const TEXTURES = {
  earth: "https://unpkg.com/three-globe@2.31.0/example/img/earth-blue-marble.jpg",
  clouds: "https://unpkg.com/three-globe@2.31.0/example/img/earth-clouds.png",
};

const EARTH_RADIUS = 2;

function latLonAltToVec3(lat: number, lon: number, alt: number): THREE.Vector3 {
  const r = EARTH_RADIUS * (1 + alt / 6371); // alt in km, Earth radius ~6371km
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  );
}

interface Props {
  lat: number | null;
  lon: number | null;
  alt: number | null;
  height?: number;
}

export default function EarthGlobe({ lat, lon, alt, height = 320 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const satRef = useRef<THREE.Mesh | null>(null);
  const simTRef = useRef(0);
  const latestRef = useRef({ lat, lon, alt });

  useEffect(() => {
    latestRef.current = { lat, lon, alt };
  }, [lat, lon, alt]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, container.clientWidth / (height || 1), 0.1, 1000);
    camera.position.set(0, 1.5, 6);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0x334466, 1.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(5, 3, 5);
    scene.add(sun);

    const loader = new THREE.TextureLoader();
    const earthMat = new THREE.MeshPhongMaterial({ color: 0x2255aa, shininess: 8 });
    const earth = new THREE.Mesh(new THREE.SphereGeometry(EARTH_RADIUS, 48, 48), earthMat);
    scene.add(earth);
    loader.load(TEXTURES.earth, (tex) => { earthMat.map = tex; earthMat.color.set(0xffffff); earthMat.needsUpdate = true; }, undefined, () => undefined);

    const cloudsMat = new THREE.MeshPhongMaterial({ transparent: true, opacity: 0.35, depthWrite: false });
    const clouds = new THREE.Mesh(new THREE.SphereGeometry(EARTH_RADIUS * 1.01, 48, 48), cloudsMat);
    scene.add(clouds);
    loader.load(TEXTURES.clouds, (tex) => { cloudsMat.map = tex; cloudsMat.needsUpdate = true; }, undefined, () => undefined);

    const starGeo = new THREE.BufferGeometry();
    const starCount = 800;
    const positions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i++) positions[i] = (Math.random() - 0.5) * 100;
    starGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.05 })));

    const satGeo = new THREE.BoxGeometry(0.12, 0.12, 0.12);
    const satMat = new THREE.MeshStandardMaterial({ color: 0x00d2ff, emissive: 0x00d2ff, emissiveIntensity: 0.6 });
    const sat = new THREE.Mesh(satGeo, satMat);
    scene.add(sat);
    satRef.current = sat;

    const orbitLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(
        Array.from({ length: 65 }, (_, i) => {
          const a = (i / 64) * Math.PI * 2;
          const r = EARTH_RADIUS * 1.18;
          return new THREE.Vector3(Math.cos(a) * r, 0, Math.sin(a) * r);
        }),
      ),
      new THREE.LineBasicMaterial({ color: 0x00d2ff, transparent: true, opacity: 0.25 }),
    );
    scene.add(orbitLine);

    let dragging = false;
    let lastX = 0, lastY = 0;
    let rotY = 0.4, rotX = 0.2;
    const onDown = (e: PointerEvent) => { dragging = true; lastX = e.clientX; lastY = e.clientY; };
    const onUp = () => { dragging = false; };
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      rotY += (e.clientX - lastX) * 0.005;
      rotX += (e.clientY - lastY) * 0.005;
      lastX = e.clientX; lastY = e.clientY;
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointermove", onMove);

    let raf = 0;
    const animate = () => {
      raf = requestAnimationFrame(animate);
      earth.rotation.y += 0.0007;
      clouds.rotation.y += 0.0011;

      let satLat = latestRef.current.lat, satLon = latestRef.current.lon;
      const satAlt = latestRef.current.alt ?? 420;
      if (satLat == null || satLon == null) {
        // No GPS fix yet — trace a simple simulated equatorial pass so the
        // globe isn't inert, same fallback spirit as the legacy viz's
        // manual test-lat/lon controls.
        simTRef.current += 0.6;
        satLat = 20 * Math.sin(simTRef.current * 0.02);
        satLon = (simTRef.current * 0.5) % 360 - 180;
      }
      const pos = latLonAltToVec3(satLat, satLon, satAlt);
      sat.position.copy(pos);
      sat.lookAt(0, 0, 0);

      camera.position.x = 6 * Math.sin(rotY) * Math.cos(rotX);
      camera.position.z = 6 * Math.cos(rotY) * Math.cos(rotX);
      camera.position.y = 6 * Math.sin(rotX) + 1;
      camera.lookAt(0, 0, 0);

      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      if (!container) return;
      camera.aspect = container.clientWidth / height;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, height);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.dispose();
      earthMat.dispose();
      cloudsMat.dispose();
      satGeo.dispose();
      satMat.dispose();
      container.innerHTML = "";
    };
    // Scene setup runs once per mount; lat/lon/alt are read live inside the
    // animation loop via latestRef, so they don't need to be dependencies.
  }, [height]);

  return (
    <div className="rounded-xl ring-1 ring-border overflow-hidden bg-card">
      <div className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Orbital Tracking
      </div>
      <div ref={containerRef} style={{ height }} className="cursor-grab active:cursor-grabbing" />
      <div className="grid grid-cols-3 gap-2 text-center font-mono text-xs px-4 pb-3">
        <div><div className="text-muted-foreground text-[10px]">LAT</div>{lat != null ? lat.toFixed(2) : "--"}°</div>
        <div><div className="text-muted-foreground text-[10px]">LON</div>{lon != null ? lon.toFixed(2) : "--"}°</div>
        <div><div className="text-muted-foreground text-[10px]">ALT</div>{alt != null ? alt.toFixed(0) : "--"} km</div>
      </div>
    </div>
  );
}
