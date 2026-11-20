/* WattWise interactive house: the real 3D scene (three.js, bundled locally, works offline).
 *
 * This file only DRAWS. It gets the state from house.js and shows it:
 *   rooms (floors, cut-away walls, windows, furniture), devices as small 3D models that
 *   animate when they are on, the EV and its charger in the driveway, energy flowing from
 *   the single meter to every device that is on, day/night lighting from the site clock.
 * It never decides or switches anything. Clicks are passed back to house.js.
 */
import * as THREE from 'three';
import { OrbitControls } from '../vendor/three/OrbitControls.js';
import { RoomEnvironment } from '../vendor/three/RoomEnvironment.js';

// ---------- sizes (metres) ----------
const ROOM_W = 5, ROOM_D = 4;        // one room
const WALL_H = 1.15;                 // cut-away walls (a "dollhouse" view)
const WALL_T = 0.12;
const DOOR_W = 1.0;

// ---------- small helpers ----------
const mat = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.8, metalness: 0, ...o });
const box = (w, h, d, m) => { const g = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); g.castShadow = true; g.receiveShadow = true; return g; };
const cyl = (rt, rb, h, m, seg = 24) => { const g = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), m); g.castShadow = true; g.receiveShadow = true; return g; };
const at = (obj, x, y, z) => { obj.position.set(x, y, z); return obj; };

function canvasTexture(w, h, draw, repeat = [1, 1]) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(...repeat);
  t.anisotropy = 4;
  return t;
}

// Procedural floor textures (no image files to download).
const TEX = {};
function textures() {
  if (TEX.wood) return TEX;
  TEX.wood = canvasTexture(512, 512, (g, w, h) => {
    const rows = 8;
    for (let r = 0; r < rows; r++) {
      let x = (r % 2) * -90;
      while (x < w) {
        const len = 160 + Math.random() * 120;
        const l = 52 + Math.random() * 12;
        g.fillStyle = `hsl(28, 38%, ${l}%)`;
        g.fillRect(x, r * h / rows, len, h / rows);
        g.strokeStyle = 'rgba(60,35,15,.35)'; g.lineWidth = 2;
        g.strokeRect(x, r * h / rows, len, h / rows);
        for (let k = 0; k < 6; k++) {   // grain
          g.strokeStyle = `rgba(90,55,25,${0.05 + Math.random() * 0.08})`; g.lineWidth = 1;
          const y = r * h / rows + Math.random() * h / rows;
          g.beginPath(); g.moveTo(x, y); g.bezierCurveTo(x + len / 3, y + 3, x + 2 * len / 3, y - 3, x + len, y); g.stroke();
        }
        x += len;
      }
    }
  }, [2, 2]);
  TEX.tile = canvasTexture(256, 256, (g, w, h) => {
    g.fillStyle = '#d9dcd6'; g.fillRect(0, 0, w, h);
    const n = 4;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      g.fillStyle = `hsl(90, 4%, ${82 + Math.random() * 6}%)`;
      g.fillRect(i * w / n + 2, j * h / n + 2, w / n - 4, h / n - 4);
    }
  }, [5, 4]);
  TEX.concrete = canvasTexture(256, 256, (g, w, h) => {
    g.fillStyle = '#8d8f8a'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 2500; i++) { g.fillStyle = `rgba(${Math.random() < .5 ? '255,255,255' : '0,0,0'},${Math.random() * 0.06})`; g.fillRect(Math.random() * w, Math.random() * h, 2, 2); }
  }, [3, 3]);
  TEX.grass = canvasTexture(256, 256, (g, w, h) => {
    g.fillStyle = '#2f4a25'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 4000; i++) { g.fillStyle = `hsla(${90 + Math.random() * 30}, 40%, ${18 + Math.random() * 20}%, .7)`; g.fillRect(Math.random() * w, Math.random() * h, 1.5, 3); }
  }, [30, 30]);
  TEX.carpet = canvasTexture(256, 256, (g, w, h) => {
    g.fillStyle = '#7d8a96'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 3000; i++) { g.fillStyle = `rgba(255,255,255,${Math.random() * 0.05})`; g.fillRect(Math.random() * w, Math.random() * h, 1, 1); }
  }, [4, 4]);
  // Energy flow: bright dashes on a dark tube; the offset moves to show the flow.
  TEX.flow = canvasTexture(64, 8, (g, w, h) => {
    g.fillStyle = '#000'; g.fillRect(0, 0, w, h);
    const grd = g.createLinearGradient(0, 0, w, 0);
    grd.addColorStop(0, 'rgba(184,240,74,0)'); grd.addColorStop(0.5, 'rgba(214,255,140,1)'); grd.addColorStop(1, 'rgba(184,240,74,0)');
    g.fillStyle = grd; g.fillRect(0, 0, w * 0.6, h);
  }, [1, 1]);
  return TEX;
}

function floorKind(id) {
  if (/bath|kitchen|kitchenette/.test(id)) return 'tile';
  if (/garage|server/.test(id)) return 'concrete';
  if (/office|meeting|training/.test(id)) return 'carpet';
  return 'wood';
}

// ---------- furniture (simple, recognisable shapes) ----------
const M = {};
function mats() {
  if (M.white) return M;
  Object.assign(M, {
    wall: mat('#e9e6df', { roughness: 0.92 }), wallTop: mat('#cfcac0'),
    white: mat('#f2f2ee', { roughness: 0.5 }), steel: mat('#b9bec4', { roughness: 0.35, metalness: 0.6 }),
    dark: mat('#2a2c2e', { roughness: 0.6 }), black: mat('#111214', { roughness: 0.4 }),
    sofa: mat('#556b7d'), cushion: mat('#6c8496'), wood: mat('#8a5a35', { roughness: 0.6 }), woodLight: mat('#b48a5f', { roughness: 0.6 }),
    bed: mat('#ecebe6'), blanket: mat('#7f9a6a'), pillow: mat('#ffffff'),
    rug: mat('#9b6b5a', { roughness: 1 }), plant: mat('#3f7a3a'), pot: mat('#a0552f'),
    glass: new THREE.MeshPhysicalMaterial({ color: '#9cc9e8', transmission: 0.6, transparent: true, opacity: 0.35, roughness: 0.05, metalness: 0 }),
    car: new THREE.MeshPhysicalMaterial({ color: '#d7dde3', metalness: 0.7, roughness: 0.25, clearcoat: 1, clearcoatRoughness: 0.1 }),
    carGlass: new THREE.MeshPhysicalMaterial({ color: '#1b2630', metalness: 0.2, roughness: 0.05, transparent: true, opacity: 0.85 }),
    tire: mat('#151515', { roughness: 0.9 }), rim: mat('#9aa0a6', { metalness: 0.8, roughness: 0.3 }),
    asphalt: mat('#3b3d3f', { roughness: 0.95 }),
  });
  return M;
}

function furniture(kind, w, d) {
  const g = new THREE.Group(); const m = mats();
  const add = (o) => (g.add(o), o);
  if (kind === 'living') {
    add(at(box(2.2, 0.4, 0.9, m.sofa), 0.2, 0.2, d / 2 - 0.75));
    add(at(box(2.2, 0.5, 0.2, m.sofa), 0.2, 0.45, d / 2 - 0.3));
    add(at(box(0.25, 0.55, 0.9, m.sofa), -0.95, 0.27, d / 2 - 0.75));
    add(at(box(0.25, 0.55, 0.9, m.sofa), 1.35, 0.27, d / 2 - 0.75));
    add(at(box(1.0, 0.06, 0.55, m.woodLight), 0.2, 0.35, 0.2));
    for (const [x, z] of [[-0.25, -0.02], [0.65, -0.02], [-0.25, 0.42], [0.65, 0.42]]) add(at(box(0.05, 0.33, 0.05, m.wood), x, 0.16, z));
    const rug = add(at(box(2.6, 0.01, 1.8, m.rug), 0.2, 0.012, 0.4)); rug.castShadow = false;
  } else if (kind === 'bed') {
    add(at(box(1.6, 0.35, 2.0, m.wood), 0.4, 0.17, 0.2));
    add(at(box(1.5, 0.18, 1.9, m.bed), 0.4, 0.43, 0.2));
    add(at(box(1.52, 0.06, 1.2, m.blanket), 0.4, 0.54, 0.55));
    add(at(box(0.6, 0.12, 0.35, m.pillow), 0.05, 0.57, -0.55));
    add(at(box(0.6, 0.12, 0.35, m.pillow), 0.75, 0.57, -0.55));
    add(at(box(1.6, 0.8, 0.08, m.wood), 0.4, 0.4, -0.82));
    add(at(box(0.45, 0.45, 0.4, m.woodLight), -0.75, 0.22, -0.6));
  } else if (kind === 'kitchen') {
    add(at(box(w - 0.6, 0.9, 0.6, m.white), 0, 0.45, -d / 2 + 0.45));
    add(at(box(w - 0.6, 0.04, 0.62, m.dark), 0, 0.92, -d / 2 + 0.45));
    add(at(box(1.2, 0.05, 0.8, m.woodLight), 0.6, 0.75, 0.6));
    for (const [x, z] of [[0.1, 0.3], [1.1, 0.3], [0.1, 0.9], [1.1, 0.9]]) add(at(box(0.05, 0.73, 0.05, m.wood), x, 0.36, z));
  } else if (kind === 'bath') {
    add(at(box(1.6, 0.55, 0.75, m.white), -w / 2 + 1.1, 0.27, -d / 2 + 0.55));
    add(at(box(0.55, 0.85, 0.45, m.white), w / 2 - 0.8, 0.42, -d / 2 + 0.4));
    add(at(box(0.4, 0.4, 0.55, m.white), 0.3, 0.2, -d / 2 + 0.45));
  } else if (kind === 'hall') {
    add(at(cyl(0.2, 0.16, 0.4, m.pot), -w / 2 + 0.6, 0.2, -d / 2 + 0.6));
    add(at(new THREE.Mesh(new THREE.IcosahedronGeometry(0.42, 1), m.plant), -w / 2 + 0.6, 0.75, -d / 2 + 0.6)).castShadow = true;
    add(at(box(1.4, 0.45, 0.4, m.woodLight), 0.6, 0.22, -d / 2 + 0.4));
  } else if (kind === 'office') {
    add(at(box(1.4, 0.05, 0.7, m.woodLight), 0, 0.75, -0.6));
    add(at(box(0.05, 0.73, 0.65, m.dark), -0.65, 0.37, -0.6));
    add(at(box(0.05, 0.73, 0.65, m.dark), 0.65, 0.37, -0.6));
    add(at(box(0.5, 0.08, 0.5, m.dark), 0, 0.45, 0.05));
    add(at(box(0.5, 0.5, 0.06, m.dark), 0, 0.72, 0.28));
  } else if (kind === 'meeting') {
    add(at(box(3.0, 0.06, 1.2, m.woodLight), 0, 0.75, 0.2));
    for (let i = 0; i < 4; i++) for (const s of [-1, 1]) add(at(box(0.45, 0.45, 0.45, m.sofa), -1.1 + i * 0.73, 0.23, 0.2 + s * 0.9));
  } else if (kind === 'server') {
    for (let i = 0; i < 2; i++) add(at(box(0.6, 1.0, 0.8, m.black), -0.6 + i * 0.75, 0.5, -d / 2 + 0.6));
  }
  return g;
}
function roomKind(id) {
  if (/living|lobby/.test(id)) return 'living';
  if (/bed|kids/.test(id)) return 'bed';
  if (/kitchen/.test(id)) return 'kitchen';
  if (/bath/.test(id)) return 'bath';
  if (/hall|corridor/.test(id)) return 'hall';
  if (/office/.test(id)) return 'office';
  if (/meeting|training/.test(id)) return 'meeting';
  if (/server/.test(id)) return 'server';
  return 'none';
}

// ---------- device models ----------
// Each returns { obj, parts, height, wall } — parts are what the animation touches.
function deviceModel(kind) {
  const m = mats(); const g = new THREE.Group(); const parts = {};
  let height = 0.6, wall = false;
  if (kind === 'ac') {
    wall = true; height = 1.15;
    g.add(at(box(0.95, 0.3, 0.24, m.white), 0, 0.95, 0));
    g.add(at(box(0.85, 0.03, 0.02, m.steel), 0, 0.84, 0.125));
    const air = new THREE.Group();
    const airMat = new THREE.MeshBasicMaterial({ color: '#9fd3ff', transparent: true, opacity: 0, depthWrite: false });
    for (let i = 0; i < 9; i++) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(0.22, 0.04), airMat.clone());
      p.userData.seed = Math.random(); p.userData.x = (Math.random() - 0.5) * 0.8;
      air.add(p);
    }
    g.add(air); parts.air = air;
    parts.led = at(new THREE.Mesh(new THREE.SphereGeometry(0.018), new THREE.MeshBasicMaterial({ color: '#333' })), 0.38, 0.9, 0.125); g.add(parts.led);
  } else if (kind === 'light') {
    height = 1.75;
    g.add(at(cyl(0.18, 0.2, 0.04, m.dark), 0, 0.02, 0));
    g.add(at(cyl(0.02, 0.02, 1.45, m.dark), 0, 0.75, 0));
    parts.shade = at(cyl(0.16, 0.28, 0.3, new THREE.MeshStandardMaterial({ color: '#f3ead8', emissive: '#ffcc77', emissiveIntensity: 0, roughness: 0.7, side: THREE.DoubleSide }), 32), 0, 1.55, 0);
    parts.shade.castShadow = false;
    g.add(parts.shade);
    parts.light = new THREE.PointLight('#ffc875', 0, 7, 1.6);
    parts.light.position.set(0, 1.45, 0);
    g.add(parts.light);
  } else if (kind === 'fan') {
    height = 1.3;
    g.add(at(cyl(0.22, 0.25, 0.05, m.dark), 0, 0.025, 0));
    g.add(at(cyl(0.025, 0.025, 1.0, m.steel), 0, 0.53, 0));
    g.add(at(cyl(0.08, 0.08, 0.16, m.white), 0, 1.06, -0.04).rotateX(Math.PI / 2));
    const cage = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.012, 8, 40), m.steel); cage.position.set(0, 1.06, 0.08); g.add(cage);
    const blades = new THREE.Group(); blades.position.set(0, 1.06, 0.08);
    const bm = new THREE.MeshStandardMaterial({ color: '#8fc7ff', roughness: 0.4, transparent: true, opacity: 0.9, side: THREE.DoubleSide });
    for (let i = 0; i < 3; i++) {
      const b = new THREE.Mesh(new THREE.CircleGeometry(0.13, 16, 0, Math.PI / 2.2), bm);
      b.rotation.z = i * Math.PI * 2 / 3; blades.add(b);
    }
    g.add(blades); parts.spin = blades; parts.spinAxis = 'z';
  } else if (kind === 'tv') {
    height = 1.2;
    g.add(at(box(1.3, 0.45, 0.4, m.wood), 0, 0.22, 0));
    g.add(at(box(1.15, 0.68, 0.05, m.black), 0, 0.95, 0));
    parts.screen = at(new THREE.Mesh(new THREE.PlaneGeometry(1.08, 0.61), new THREE.MeshStandardMaterial({ color: '#05070a', emissive: '#3b82c4', emissiveIntensity: 0, roughness: 0.3 })), 0, 0.95, 0.027);
    g.add(parts.screen);
    parts.glow = new THREE.PointLight('#5aa7ff', 0, 3, 2); parts.glow.position.set(0, 0.95, 0.4); g.add(parts.glow);
  } else if (kind === 'heater') {
    wall = true; height = 1.6;
    g.add(at(cyl(0.25, 0.25, 0.95, m.white, 32), 0, 0.95, 0));
    g.add(at(cyl(0.255, 0.255, 0.06, m.steel, 32), 0, 1.44, 0));
    parts.ring = at(new THREE.Mesh(new THREE.TorusGeometry(0.255, 0.02, 8, 40), new THREE.MeshStandardMaterial({ color: '#552', emissive: '#ff5a1f', emissiveIntensity: 0 })), 0, 0.7, 0);
    parts.ring.rotation.x = Math.PI / 2; g.add(parts.ring);
    const heat = new THREE.Group();
    for (let i = 0; i < 6; i++) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(0.05, 0.22), new THREE.MeshBasicMaterial({ color: '#ff8a4a', transparent: true, opacity: 0, depthWrite: false }));
      p.userData.seed = Math.random(); p.userData.x = (Math.random() - 0.5) * 0.4; heat.add(p);
    }
    g.add(heat); parts.heat = heat;
  } else if (kind === 'washer') {
    height = 0.95;
    g.add(at(box(0.6, 0.85, 0.6, m.white), 0, 0.425, 0));
    g.add(at(new THREE.Mesh(new THREE.TorusGeometry(0.19, 0.03, 10, 32), m.steel), 0, 0.42, 0.305));
    const drum = new THREE.Group(); drum.position.set(0, 0.42, 0.3);
    drum.add(new THREE.Mesh(new THREE.CircleGeometry(0.17, 24), new THREE.MeshStandardMaterial({ color: '#2b3a48', roughness: 0.2, metalness: 0.4 })));
    const fin = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.04), new THREE.MeshBasicMaterial({ color: '#8fc7ff' })); fin.position.z = 0.002; drum.add(fin);
    g.add(drum); parts.spin = drum; parts.spinAxis = 'z';
  } else if (kind === 'fridge') {
    height = 1.85;
    g.add(at(box(0.7, 1.75, 0.65, m.steel), 0, 0.875, 0));
    g.add(at(box(0.68, 0.01, 0.01, m.dark), 0, 1.15, 0.33));
    g.add(at(box(0.03, 0.4, 0.03, m.dark), 0.28, 1.4, 0.34));
    g.add(at(box(0.03, 0.4, 0.03, m.dark), 0.28, 0.8, 0.34));
  } else if (kind === 'router' || kind === 'pc') {
    height = kind === 'pc' ? 1.25 : 0.95;
    if (kind === 'pc') {
      g.add(at(box(0.9, 0.04, 0.5, m.woodLight), 0, 0.74, 0));
      g.add(at(box(0.6, 0.38, 0.03, m.black), 0, 1.0, -0.1));
      parts.screen = at(new THREE.Mesh(new THREE.PlaneGeometry(0.56, 0.33), new THREE.MeshStandardMaterial({ color: '#05070a', emissive: '#4a9be0', emissiveIntensity: 0 })), 0, 1.0, -0.084);
      g.add(parts.screen);
    } else {
      g.add(at(box(0.5, 0.75, 0.35, m.woodLight), 0, 0.37, 0));
      g.add(at(box(0.32, 0.06, 0.2, m.dark), 0, 0.78, 0));
      for (const x of [-0.13, 0.13]) g.add(at(cyl(0.008, 0.008, 0.22, m.dark), x, 0.9, -0.08));
      parts.leds = [];
      for (let i = 0; i < 3; i++) { const l = at(new THREE.Mesh(new THREE.SphereGeometry(0.012), new THREE.MeshBasicMaterial({ color: '#333' })), -0.06 + i * 0.06, 0.79, 0.101); g.add(l); parts.leds.push(l); }
    }
  } else if (kind === 'fire_alarm' || kind === 'emergency_light') {
    wall = true; height = 1.15;
    if (kind === 'fire_alarm') g.add(at(cyl(0.1, 0.1, 0.05, m.white), 0, 1.05, 0).rotateX(Math.PI / 2));
    else g.add(at(box(0.4, 0.12, 0.08, m.white), 0, 1.0, 0));
    parts.leds = [at(new THREE.Mesh(new THREE.SphereGeometry(0.02), new THREE.MeshBasicMaterial({ color: '#333' })), 0, kind === 'fire_alarm' ? 1.05 : 1.0, 0.05)];
    g.add(parts.leds[0]);
  } else if (kind === 'ev') {
    wall = true; height = 1.4;
    g.add(at(box(0.32, 0.45, 0.14, m.white), 0, 1.05, 0));
    parts.ring = at(new THREE.Mesh(new THREE.TorusGeometry(0.07, 0.012, 8, 24), new THREE.MeshStandardMaterial({ color: '#222', emissive: '#b8f04a', emissiveIntensity: 0 })), 0, 1.1, 0.072);
    g.add(parts.ring);
  } else {
    height = 0.5;
    g.add(at(box(0.3, 0.12, 0.2, m.dark), 0, 0.06, 0));
  }
  g.traverse(o => { if (o.isMesh && o.material && o.material.transparent) o.castShadow = false; });
  return { obj: g, parts, height, wall };
}

function carModel() {
  const m = mats(); const g = new THREE.Group();
  const body = new THREE.Shape();
  body.moveTo(-2.1, 0.25); body.lineTo(2.1, 0.25); body.quadraticCurveTo(2.25, 0.3, 2.2, 0.62);
  body.lineTo(1.2, 0.78); body.quadraticCurveTo(0.6, 1.25, 0, 1.28); body.lineTo(-1.0, 1.25);
  body.quadraticCurveTo(-1.8, 1.15, -2.1, 0.8); body.lineTo(-2.15, 0.35); body.closePath();
  const geo = new THREE.ExtrudeGeometry(body, { depth: 1.7, bevelEnabled: true, bevelSize: 0.08, bevelThickness: 0.08, bevelSegments: 3 });
  geo.translate(0, 0, -0.85);
  const shell = new THREE.Mesh(geo, m.car); shell.castShadow = true; shell.receiveShadow = true; g.add(shell);
  const win = new THREE.Shape();
  win.moveTo(1.05, 0.82); win.quadraticCurveTo(0.55, 1.2, 0, 1.22); win.lineTo(-0.95, 1.19); win.quadraticCurveTo(-1.55, 1.1, -1.75, 0.85); win.closePath();
  const wgeo = new THREE.ExtrudeGeometry(win, { depth: 1.78, bevelEnabled: false }); wgeo.translate(0, 0.02, -0.89);
  g.add(new THREE.Mesh(wgeo, m.carGlass));
  for (const x of [-1.35, 1.35]) for (const z of [-0.86, 0.86]) {
    const t = cyl(0.36, 0.36, 0.24, m.tire, 28); t.rotation.x = Math.PI / 2; t.position.set(x, 0.36, z); g.add(t);
    const r = cyl(0.22, 0.22, 0.25, m.rim, 20); r.rotation.x = Math.PI / 2; r.position.set(x, 0.36, z); g.add(r);
  }
  const lamp = new THREE.MeshStandardMaterial({ color: '#fff', emissive: '#ffffff', emissiveIntensity: 0.6 });
  for (const z of [-0.6, 0.6]) g.add(at(box(0.05, 0.08, 0.35, lamp), 2.22, 0.58, z));
  const tail = new THREE.MeshStandardMaterial({ color: '#600', emissive: '#ff2a2a', emissiveIntensity: 0.4 });
  g.add(at(box(0.05, 0.06, 1.5, tail), -2.17, 0.75, 0));
  // Charging port light (green when charging) on the left rear side.
  const port = at(new THREE.Mesh(new THREE.CircleGeometry(0.06, 16), new THREE.MeshStandardMaterial({ color: '#111', emissive: '#b8f04a', emissiveIntensity: 0 })), -1.55, 0.85, 0.94);
  g.add(port);
  return { obj: g, port };
}

// ---------- the scene ----------
export function createHouse(container, handlers) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.fog = new THREE.Fog('#0d1117', 40, 90);

  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.maxPolarAngle = Math.PI * 0.47; controls.minDistance = 4; controls.maxDistance = 60;
  controls.target.set(0, 0, 0);

  const hemi = new THREE.HemisphereLight('#bcd4ff', '#2b2a22', 0.6); scene.add(hemi);
  const sun = new THREE.DirectionalLight('#fff3dd', 2.2);
  sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.02;
  scene.add(sun); scene.add(sun.target);

  const world = new THREE.Group(); scene.add(world);
  const S = {
    rooms: {}, devs: {}, wires: {}, anchors: {}, meterPos: new THREE.Vector3(), car: null, cable: null,
    bounds: { w: 10, d: 8 }, view: 'iso', tween: null, night: 1, pulse: 0,
  };

  // ---- build from the state (rooms and devices) ----
  function build(st, opts = {}) {
    world.clear();
    S.rooms = {}; S.devs = {}; S.wires = {}; S.anchors = {}; S.car = null; S.cable = null;
    textures(); mats();
    const inside = st.rooms.filter(r => r.id !== 'garage');
    const garage = st.rooms.find(r => r.id === 'garage');
    const n = inside.length;
    const cols = opts.narrow ? Math.min(n, 2) : n <= 3 ? n : n <= 6 ? 3 : 4;
    const rows = Math.ceil(n / cols);
    const W = cols * ROOM_W, D = rows * ROOM_D;
    const x0 = -W / 2, z0 = -D / 2;
    const pos = {};
    inside.forEach((r, i) => {
      const c = i % cols, row = Math.floor(i / cols);
      pos[r.id] = { x: x0 + (cols - 1 - c) * ROOM_W, z: z0 + row * ROOM_D, w: ROOM_W, d: ROOM_D, c, row };
    });
    if (garage) pos.garage = { x: x0 - ROOM_W - 0.4, z: z0 + D - ROOM_D, w: ROOM_W, d: ROOM_D, garage: true };
    S.bounds = { w: W + (garage ? ROOM_W + 0.4 : 0), d: D, cx: garage ? -(ROOM_W + 0.4) / 2 : 0 };

    // ground, path, driveway
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(160, 160), new THREE.MeshStandardMaterial({ map: TEX.grass, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; world.add(ground);
    const pathM = mat('#a8a49b', { roughness: 0.95 });
    const path = box(1.4, 0.02, 6, pathM); path.position.set(0, 0.01, D / 2 + 3); path.castShadow = false; world.add(path);
    if (garage) {
      const p = pos.garage;
      const drive = box(ROOM_W - 0.6, 0.02, 9, M.asphalt); drive.position.set(p.x + ROOM_W / 2, 0.011, z0 + D + 4.5); drive.castShadow = false; world.add(drive);
    }
    // plinth under the house
    const plinth = box(W + 0.3, 0.12, D + 0.3, mat('#6f6c66')); plinth.position.set(0, 0.06, 0); world.add(plinth);

    // rooms
    for (const r of st.rooms) {
      const p = pos[r.id]; if (!p) continue;
      const cx = p.x + p.w / 2, cz = p.z + p.d / 2;
      const room = new THREE.Group(); room.position.set(cx, 0.12, cz); world.add(room);
      const fk = floorKind(r.id);
      const floorMat = new THREE.MeshStandardMaterial({ map: TEX[fk], roughness: fk === 'tile' ? 0.35 : fk === 'wood' ? 0.6 : 0.9, color: '#ffffff' });
      const floor = new THREE.Mesh(new THREE.BoxGeometry(p.w - 0.02, 0.04, p.d - 0.02), floorMat);
      floor.position.y = 0.0; floor.receiveShadow = true; floor.userData = { room: r.id };
      if (p.garage) floor.position.y = -0.1;
      room.add(floor);
      // glow overlay for waste / pending / selected
      const over = new THREE.Mesh(new THREE.PlaneGeometry(p.w - 0.1, p.d - 0.1), new THREE.MeshBasicMaterial({ color: '#e8553f', transparent: true, opacity: 0, depthWrite: false }));
      over.rotation.x = -Math.PI / 2; over.position.y = 0.03 + (p.garage ? -0.1 : 0); room.add(over);
      const edge = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(p.w - 0.06, 0.02, p.d - 0.06)), new THREE.LineBasicMaterial({ color: '#b8f04a', transparent: true, opacity: 0 }));
      edge.position.y = 0.04 + (p.garage ? -0.1 : 0); room.add(edge);
      // furniture
      const f = furniture(roomKind(r.id), p.w, p.d); f.position.y = 0.02; room.add(f);
      S.rooms[r.id] = { group: room, floor, over, edge, p, center: new THREE.Vector3(cx, 0, cz), windowGlass: null };
      S.anchors['room:' + r.id] = new THREE.Vector3(cx, 1.9, cz + 0.4);
      S.anchors['tag:' + r.id] = new THREE.Vector3(cx, 2.9, cz + 0.4);
    }

    // walls: every room draws its north and west walls; the edge of the house closes the rest
    const wallMat = M.wall;
    const addWall = (x1, z1, x2, z2, door, outside, roomId) => {
      const len = Math.hypot(x2 - x1, z2 - z1), horiz = Math.abs(z2 - z1) < 1e-6;
      const segs = door ? [[0, len / 2 - DOOR_W / 2], [len / 2 + DOOR_W / 2, len]] : [[0, len]];
      for (const [a, b] of segs) {
        const l = b - a; if (l <= 0.01) continue;
        const wbox = box(horiz ? l : WALL_T, WALL_H, horiz ? WALL_T : l, wallMat);
        const mid = (a + b) / 2;
        wbox.position.set(horiz ? x1 + mid : x1, 0.12 + WALL_H / 2, horiz ? z1 : z1 + mid);
        world.add(wbox);
        const cap = box(horiz ? l : WALL_T + 0.01, 0.015, horiz ? WALL_T + 0.01 : l, M.wallTop);
        cap.position.set(wbox.position.x, 0.12 + WALL_H + 0.008, wbox.position.z); cap.castShadow = false; world.add(cap);
      }
      if (outside && roomId) {   // a window on outside walls
        const gw = 1.4;
        const glass = new THREE.Mesh(new THREE.BoxGeometry(horiz ? gw : 0.03, 0.5, horiz ? 0.03 : gw), M.glass);
        const mx = (x1 + x2) / 2, mz = (z1 + z2) / 2;
        glass.position.set(mx, 0.12 + WALL_H + 0.25, mz);
        const frame = new THREE.LineSegments(new THREE.EdgesGeometry(glass.geometry), new THREE.LineBasicMaterial({ color: '#d8d8d8' }));
        glass.add(frame);
        world.add(glass);
        if (!S.rooms[roomId].windowGlass) S.rooms[roomId].windowGlass = { mesh: glass, horiz, base: glass.position.clone() };
      }
    };
    for (const r of inside) {
      const p = pos[r.id];
      const north = !inside.some(o => pos[o.id].row === p.row - 1 && pos[o.id].c === p.c);
      const westCell = inside.find(o => pos[o.id].row === p.row && pos[o.id].c === p.c + 1);   // RTL: c+1 is to the west
      const eastCell = inside.find(o => pos[o.id].row === p.row && pos[o.id].c === p.c - 1);
      const south = !inside.some(o => pos[o.id].row === p.row + 1 && pos[o.id].c === p.c);
      addWall(p.x, p.z, p.x + p.w, p.z, !north, north, north ? r.id : null);
      addWall(p.x, p.z, p.x, p.z + p.d, !!westCell, !westCell, !westCell ? null : null);
      if (!eastCell) addWall(p.x + p.w, p.z, p.x + p.w, p.z + p.d, false, true, null);
      if (south) addWall(p.x, p.z + p.d, p.x + p.w, p.z + p.d, r.id === inside[Math.floor(cols / 2)]?.id, false, null);
    }
    if (garage) {   // a carport: back wall and a light roof on posts
      const p = pos.garage;
      addWall(p.x, p.z, p.x + p.w, p.z, false, false, null);
      const roof = box(p.w + 0.4, 0.06, p.d + 0.6, new THREE.MeshPhysicalMaterial({ color: '#cfd6dc', transparent: true, opacity: 0.18, roughness: 0.2 }));
      roof.position.set(p.x + p.w / 2, 2.6, p.z + p.d / 2 + 0.2); roof.castShadow = false; world.add(roof);
      S.carportRoof = roof;
      for (const [x, z] of [[p.x + 0.1, p.z + p.d + 0.4], [p.x + p.w - 0.1, p.z + p.d + 0.4], [p.x + 0.1, p.z + 0.05], [p.x + p.w - 0.1, p.z + 0.05]]) {
        const post = cyl(0.05, 0.05, 2.6, M.steel); post.position.set(x, 1.3, z); world.add(post);
      }
    }

    // the main meter: a grey box on the south wall near the front door
    const doorRoom = inside[Math.floor(cols / 2)] || inside[0];
    const dp = pos[doorRoom.id];
    S.meterPos.set(dp.x + dp.w / 2 + 1.0, 0.12, z0 + D + 0.18);
    const meterBox = box(0.4, 0.55, 0.16, mat('#d6d6d0', { roughness: 0.5 })); meterBox.position.set(S.meterPos.x, 0.12 + 0.7, S.meterPos.z); world.add(meterBox);
    S.meterScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.28, 0.14), new THREE.MeshStandardMaterial({ color: '#0b0f05', emissive: '#b8f04a', emissiveIntensity: 0.8 }));
    S.meterScreen.position.set(S.meterPos.x, 0.12 + 0.78, S.meterPos.z + 0.081); world.add(S.meterScreen);
    S.anchors.meter = new THREE.Vector3(S.meterPos.x + 0.9, 0.5, S.meterPos.z + 0.9);
    const busZ = z0 + D + 0.45;

    // devices
    const used = {};
    for (const d of st.devices) {
      const p = pos[d.room]; if (!p) continue;
      const model = deviceModel(d.kind);
      const k = used[d.room] = (used[d.room] || 0) + 1;
      const list = st.devices.filter(x => x.room === d.room);
      const idx = list.indexOf(d), total = list.length;
      let x, z, rotY = 0;
      if (p.garage && d.kind === 'ev') {
        x = p.x + 0.9; z = p.z + 0.12;
      } else if (model.wall) {
        // on the north wall, spread along it
        const wallOnes = list.filter(o => deviceModel(o.kind).wall);
        const wi = wallOnes.indexOf(d);
        x = p.x + p.w * (wi + 1) / (wallOnes.length + 1); z = p.z + 0.14;
      } else {
        const floorOnes = list.filter(o => !deviceModel(o.kind).wall);
        const fi = floorOnes.indexOf(d);
        const spots = [[0.25, 0.32], [0.75, 0.32], [0.5, 0.3], [0.2, 0.62], [0.82, 0.62]];
        const sp = spots[fi % spots.length];
        x = p.x + p.w * sp[0]; z = p.z + p.d * sp[1];
        if (d.kind === 'tv') { x = p.x + p.w * 0.45; z = p.z + 0.5; }
      }
      model.obj.position.set(x, 0.14 + (p.garage ? -0.1 : 0), z);
      model.obj.rotation.y = rotY;
      model.obj.traverse(o => { o.userData.device = d.id; });
      world.add(model.obj);
      S.devs[d.id] = { ...model, kind: d.kind, pos: new THREE.Vector3(x, 0, z) };
      S.anchors['dev:' + d.id] = new THREE.Vector3(x, model.height + 0.35, z);
      // wire: meter -> bus along the front of the house -> up into the room -> device
      const entryX = p.x + p.w / 2;
      const pts = [
        new THREE.Vector3(S.meterPos.x, 0.16, S.meterPos.z + 0.25),
        new THREE.Vector3(S.meterPos.x, 0.16, busZ),
        new THREE.Vector3(entryX, 0.16, busZ),
        new THREE.Vector3(entryX, 0.16 + (p.garage ? -0.08 : 0), z + 0.35),
        new THREE.Vector3(x, 0.16 + (p.garage ? -0.08 : 0), z + 0.35),
      ];
      const curve = new THREE.CurvePath();
      for (let i = 0; i < pts.length - 1; i++) if (pts[i].distanceTo(pts[i + 1]) > 0.01) curve.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
      const length = curve.getLength();
      const flowTex = TEX.flow.clone(); flowTex.needsUpdate = true; flowTex.repeat.set(Math.max(1, length / 0.6), 1);
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(8, Math.round(length * 6)), 0.025, 6, false),
        new THREE.MeshBasicMaterial({ map: flowTex, color: '#b8f04a', transparent: true, opacity: 0.0, blending: THREE.AdditiveBlending, depthWrite: false }));
      const base = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(8, Math.round(length * 6)), 0.018, 6, false), new THREE.MeshStandardMaterial({ color: '#2b2e26', roughness: 0.8 }));
      world.add(base); world.add(tube);
      S.wires[d.id] = { tube, tex: flowTex };

      if (d.kind === 'ev' && p.garage) {
        const car = carModel();
        car.obj.rotation.y = Math.PI / 2;
        car.obj.position.set(p.x + p.w / 2 + 0.2, 0.04, p.z + p.d / 2 + 0.3);
        world.add(car.obj);
        S.car = car;
        // charging cable from the wallbox to the car port
        const portWorld = new THREE.Vector3(p.x + p.w / 2 + 0.2 + 0.94, 0.85, p.z + p.d / 2 + 0.3 + 1.55);
        car.obj.updateMatrixWorld(); const pw = car.port.getWorldPosition(new THREE.Vector3());
        const a = new THREE.Vector3(x, 1.0, z + 0.1);
        const cc = new THREE.CatmullRomCurve3([a, new THREE.Vector3(a.x, 0.2, a.z + 0.4), new THREE.Vector3((a.x + pw.x) / 2, 0.08, (a.z + pw.z) / 2), new THREE.Vector3(pw.x - 0.1, 0.4, pw.z), pw]);
        void portWorld;
        const ctex = TEX.flow.clone(); ctex.needsUpdate = true; ctex.repeat.set(8, 1);
        world.add(new THREE.Mesh(new THREE.TubeGeometry(cc, 60, 0.03, 8, false), new THREE.MeshStandardMaterial({ color: '#1b1c1e', roughness: 0.6 })));
        const glowC = new THREE.Mesh(new THREE.TubeGeometry(cc, 60, 0.036, 8, false), new THREE.MeshBasicMaterial({ map: ctex, color: '#b8f04a', transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
        world.add(glowC);
        S.cable = { mesh: glowC, tex: ctex };
        S.anchors.car = new THREE.Vector3(car.obj.position.x, 2.0, car.obj.position.z);
      }
    }
    resize();
    setView(S.view, true);
  }

  // ---- camera ----
  function homeCamera(view) {
    const b = S.bounds; const span = Math.max(b.w, b.d * 1.3);
    const aspect = renderer.domElement.clientWidth / Math.max(1, renderer.domElement.clientHeight);
    const dist = span * (aspect < 1 ? 1.5 : 1.02) + 2;
    if (view === 'top') return { pos: new THREE.Vector3(b.cx, dist * 1.15, 0.01), target: new THREE.Vector3(b.cx, 0, 0) };
    return { pos: new THREE.Vector3(b.cx + dist * 0.55, dist * 0.62, dist * 0.78), target: new THREE.Vector3(b.cx, 0, 0.3) };
  }
  function flyTo(pos, target, ms = 1100) {
    S.tween = { from: camera.position.clone(), to: pos, tFrom: controls.target.clone(), tTo: target, t0: performance.now(), ms };
  }
  function setView(view, instant) {
    S.view = view;
    const c = homeCamera(view);
    if (instant) { camera.position.copy(c.pos); controls.target.copy(c.target); controls.update(); }
    else flyTo(c.pos, c.target);
  }
  function focusRoom(id) {
    const r = S.rooms[id]; if (!r) return;
    const c = r.center;
    flyTo(new THREE.Vector3(c.x + 4.2, 6.2, c.z + 7.5), new THREE.Vector3(c.x, 0.4, c.z));
  }
  function focusPoint(v, d = 6) { flyTo(new THREE.Vector3(v.x + d * 0.6, d * 0.8, v.z + d), new THREE.Vector3(v.x, 0.5, v.z)); }

  // ---- update from the state (every second) ----
  function update(st, ui) {
    S.st = st; S.ui = ui;
    // day / night from the site clock
    const [hh, mm] = (st.clock || '20:00').split(':').map(Number);
    const h = hh + mm / 60;
    const day = Math.max(0, Math.min(1, (Math.min(h - 5.5, 19 - h)) / 1.5));   // 0 night .. 1 day
    S.night = 1 - day;
    const pend = ui.pendingDevice;
    for (const r of st.rooms) {
      const R = S.rooms[r.id]; if (!R) continue;
      R.state = pend && st.devices.find(d => d.id === pend)?.room === r.id ? 'pend' : r.waste ? 'waste' : null;
      R.sel = ui.room === r.id;
      if (R.windowGlass) {
        const open = r.window_open === true;
        R.windowGlass.mesh.material = open ? new THREE.MeshPhysicalMaterial({ color: '#8fc7ff', transparent: true, opacity: 0.55, emissive: '#3b8ad8', emissiveIntensity: 0.6 }) : M.glass;
        R.windowGlass.mesh.position.y = R.windowGlass.base.y + (open ? 0.35 : 0);
      }
    }
    const maxW = Math.max(60, ...st.devices.map(d => d.est_w));
    for (const d of st.devices) {
      const D = S.devs[d.id]; if (!D) continue;
      D.on = d.is_on; D.w = d.est_w; D.frac = d.is_on ? Math.min(1, d.est_w / maxW) : 0;
      if (d.kind === 'ev') { D.on = !!(st.ev && st.ev.charging); D.frac = D.on ? 1 : 0; }
    }
  }

  // ---- animation loop ----
  const clock = new THREE.Clock();
  let raf = 0;
  function frame() {
    raf = requestAnimationFrame(frame);
    const dt = Math.min(0.05, clock.getDelta()); const t = clock.elapsedTime;
    S.pulse = 0.5 + 0.5 * Math.sin(t * 4);
    if (S.tween) {
      const k = Math.min(1, (performance.now() - S.tween.t0) / S.tween.ms);
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      camera.position.lerpVectors(S.tween.from, S.tween.to, e);
      controls.target.lerpVectors(S.tween.tFrom, S.tween.tTo, e);
      if (k >= 1) S.tween = null;
    }
    controls.update();

    // lighting
    const night = S.night;
    renderer.toneMappingExposure = 1.0 - night * 0.25;
    sun.intensity = 2.4 * (1 - night) + 0.25 * night;
    sun.color.set(night > 0.5 ? '#8fa8d8' : '#fff1d6');
    const b = S.bounds;
    sun.position.set(b.cx + (night > 0.5 ? -12 : 14), 22, 12); sun.target.position.set(b.cx, 0, 0);
    const sh = Math.max(b.w, b.d) * 0.85 + 4;
    Object.assign(sun.shadow.camera, { left: -sh, right: sh, top: sh, bottom: -sh, near: 1, far: 70 }); sun.shadow.camera.updateProjectionMatrix();
    hemi.intensity = 0.65 * (1 - night) + 0.18 * night;
    const sky = new THREE.Color('#9ec3e6').lerp(new THREE.Color('#0b1020'), night);
    scene.background = sky; scene.fog.color.copy(sky);
    scene.environmentIntensity = 0.55 * (1 - night) + 0.12 * night;

    // rooms
    for (const R of Object.values(S.rooms)) {
      const col = R.state === 'pend' ? '#f2b544' : R.state === 'waste' ? '#e8553f' : null;
      if (col) { R.over.material.color.set(col); R.over.material.opacity = 0.18 + 0.22 * S.pulse; }
      else R.over.material.opacity = Math.max(0, R.over.material.opacity - dt);
      R.edge.material.opacity = R.sel ? 0.95 : 0;
    }

    // devices
    for (const D of Object.values(S.devs)) {
      const on = !!D.on, P = D.parts;
      if (P.light) {
        const target = on ? 6 + 10 * night : 0;
        P.light.intensity += (target - P.light.intensity) * 0.15;
        P.shade.material.emissiveIntensity += ((on ? 1.4 : 0) - P.shade.material.emissiveIntensity) * 0.15;
      }
      if (P.spin) {
        D.spd = (D.spd || 0) + (((on ? 6 + 14 * D.frac : 0)) - (D.spd || 0)) * dt * 1.5;
        P.spin.rotation.z += D.spd * dt;
      }
      if (P.air) P.air.children.forEach(p => {
        const k = (t * 0.6 + p.userData.seed) % 1;
        p.position.set(p.userData.x, 0.8 - k * 0.55, 0.16 + k * 0.6);
        p.material.opacity = on ? 0.55 * Math.sin(k * Math.PI) : Math.max(0, p.material.opacity - dt);
      });
      if (P.led) P.led.material.color.set(on ? '#7cff6b' : '#333');
      if (P.heat) P.heat.children.forEach(p => {
        const k = (t * 0.5 + p.userData.seed) % 1;
        p.position.set(p.userData.x, 1.5 + k * 0.6, 0);
        p.material.opacity = on ? 0.6 * Math.sin(k * Math.PI) : 0;
        p.quaternion.copy(camera.quaternion);
      });
      if (P.ring) P.ring.material.emissiveIntensity = on ? (D.kind === 'ev' ? 0.8 + 0.8 * S.pulse : 1.5) : 0;
      if (P.screen) P.screen.material.emissiveIntensity = on ? 0.9 + 0.25 * Math.sin(t * 7 + Math.sin(t * 3) * 2) : 0;
      if (P.glow) P.glow.intensity = on ? 1.2 + 0.4 * Math.sin(t * 7) : 0;
      if (P.leds) P.leds.forEach((l, i) => l.material.color.set(on && Math.sin(t * 6 + i * 2) > -0.2 ? (D.kind === 'fire_alarm' ? '#ff3b30' : '#7cff6b') : '#333'));
    }
    for (const [id, W] of Object.entries(S.wires)) {
      const D = S.devs[id];
      const live = D && D.on && (D.w > 0 || D.kind === 'ev');
      W.tube.material.opacity += ((live ? 0.95 : 0) - W.tube.material.opacity) * 0.1;
      if (live) W.tex.offset.x -= dt * (0.6 + 2.6 * (D.frac || 0));
    }
    if (S.cable) {
      const on = S.devs[Object.keys(S.devs).find(k => S.devs[k].kind === 'ev')]?.on;
      S.cable.mesh.material.opacity += ((on ? 1 : 0) - S.cable.mesh.material.opacity) * 0.1;
      if (on) S.cable.tex.offset.x -= dt * 2.4;
      if (S.car) S.car.port.material.emissiveIntensity = on ? 0.8 + 0.8 * S.pulse : 0;
    }

    renderer.render(scene, camera);
    if (handlers.onFrame) handlers.onFrame();
  }

  // ---- picking (click a room or a device) ----
  const ray = new THREE.Raycaster(); const ndc = new THREE.Vector2();
  let down = null;
  renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return;
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(world.children, true).find(h => h.object.userData.device || h.object.userData.room);
    if (!hit) return;
    if (hit.object.userData.device) handlers.onDevice && handlers.onDevice(hit.object.userData.device);
    else handlers.onRoom && handlers.onRoom(hit.object.userData.room);
  });
  renderer.domElement.addEventListener('dblclick', () => setView(S.view));

  // ---- screen positions for the HTML labels ----
  const v = new THREE.Vector3();
  function project(key) {
    const a = S.anchors[key]; if (!a) return null;
    v.copy(a).project(camera);
    const w = renderer.domElement.clientWidth, h = renderer.domElement.clientHeight;
    return { x: (v.x + 1) / 2 * w, y: (1 - v.y) / 2 * h, behind: v.z > 1, dist: camera.position.distanceTo(a) };
  }

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = w + 'px'; renderer.domElement.style.height = h + 'px';
    camera.aspect = w / Math.max(1, h); camera.updateProjectionMatrix();
  }
  new ResizeObserver(() => { resize(); }).observe(container);
  document.addEventListener('visibilitychange', () => { if (document.hidden) cancelAnimationFrame(raf); else { clock.getDelta(); frame(); } });
  frame();

  return { build, update, setView, focusRoom, focusPoint, project, get anchors() { return S.anchors; }, home: () => setView(S.view), get view() { return S.view; } };
}
