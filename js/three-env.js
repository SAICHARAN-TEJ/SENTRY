/**
 * SUBPIXEL-SENTRY // PHOTOREALISTIC 3D TACTICAL RECONNAISSANCE ENGINE
 * Three.js R170 + Texture-Mapped Himalayan DEM + Sentinel-2 Low-Earth Orbit Pass
 * Volumetric Push-Broom Sensor Cone, Realistic Solar Glancing Lighting & Sector Flyovers.
 * Zero AI Slop: Built to defense aerospace specifications.
 */

class SentryEnvironment {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;

    this.clock = new THREE.Clock();
    this.ready = false;
    this.activeAoi = 'AOI_01';

    // Camera navigation state
    this.cameraMode = 'ORBIT'; // ORBIT or FLYOVER
    this.cameraPos = new THREE.Vector3(0, 36, 52);
    this.cameraTarget = new THREE.Vector3(0, 4, 0);
    this.desiredPos = this.cameraPos.clone();
    this.desiredTarget = this.cameraTarget.clone();

    // Mouse drag interaction
    this.isMouseDown = false;
    this.previousMousePosition = { x: 0, y: 0 };
    this.spherical = { radius: 64, phi: Math.PI / 3.4, theta: 0.1 };

    // Sector waypoints for cinematic tactical flyovers
    this.sectorWaypoints = {
      AOI_01: { // Sector Tawang — LAC Forward Area
        target: new THREE.Vector3(-4, 6, 2),
        camOffset: new THREE.Vector3(-18, 28, 40),
        name: "SECTOR TAWANG // 27.5861° N, 91.8594° E",
        elev: "4,320m ASL"
      },
      AOI_02: { // Sector Pangong — North Finger Ridge
        target: new THREE.Vector3(12, 4, -8),
        camOffset: new THREE.Vector3(30, 24, 28),
        name: "SECTOR PANGONG // 33.7297° N, 78.5882° E",
        elev: "4,250m ASL"
      },
      AOI_03: { // Sector DBO — Caravan Depot
        target: new THREE.Vector3(2, 8, -14),
        camOffset: new THREE.Vector3(8, 38, 32),
        name: "SECTOR DBO // 35.2912° N, 77.9288° E",
        elev: "5,100m ASL"
      }
    };

    this._initRenderer();
    this._initScene();
    this._initCamera();
    this._initLights();
    this._loadTexturesAndBuildTerrain();
    this._buildSentinel2Satellite();
    this._buildSensorFrustum();
    this._buildTacticalReticles();
    this._initPostProcessing();
    this._initControls();

    this.ready = true;
    this._animate();
  }

  _initRenderer() {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance'
    });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.setClearColor(0x000002, 1);
  }

  _initScene() {
    this.scene = new THREE.Scene();
    // Atmospheric fog: deep space night falling off to dark horizon
    this.scene.fog = new THREE.FogExp2(0x020206, 0.0035);

    // Realistic deep space starfield (faint, non-twinkling, celestial reference)
    const starCount = 1200;
    const starGeo = new THREE.BufferGeometry();
    const starPos = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i += 3) {
      const r = 400 + Math.random() * 200;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      starPos[i] = r * Math.sin(phi) * Math.cos(theta);
      starPos[i + 1] = Math.abs(r * Math.cos(phi)) + 40; // Upper celestial sphere
      starPos[i + 2] = r * Math.sin(phi) * Math.sin(theta);
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
    const starMat = new THREE.PointsMaterial({
      color: 0xd8e2ec,
      size: 1.2,
      transparent: true,
      opacity: 0.65,
      sizeAttenuation: false
    });
    this.stars = new THREE.Points(starGeo, starMat);
    this.scene.add(this.stars);
  }

  _initCamera() {
    this.camera = new THREE.PerspectiveCamera(
      42,
      window.innerWidth / window.innerHeight,
      0.5,
      1500
    );
    this._updateSphericalPosition();
  }

  _initLights() {
    // 1. Primary Low-Angle Sun (Himalayan morning sun at LAC, 38° elevation)
    this.sunLight = new THREE.DirectionalLight(0xfff7ea, 2.8);
    this.sunLight.position.set(65, 45, 55);
    this.scene.add(this.sunLight);

    // 2. High-Altitude Cold Ambient Fill (Diffuse blue sky reflection)
    const hemiLight = new THREE.HemisphereLight(0x2a3b5c, 0x020204, 0.45);
    this.scene.add(hemiLight);

    // 3. Counter-light for deep shadowed gorge fill
    const gorgeFill = new THREE.DirectionalLight(0x182436, 0.4);
    gorgeFill.position.set(-60, 10, -40);
    this.scene.add(gorgeFill);
  }

  _loadTexturesAndBuildTerrain() {
    const loader = new THREE.TextureLoader();
    const terrainSize = 160;
    const segments = 220;

    const diffuse = loader.load('/assets/terrain_diffuse.jpg');
    const height = loader.load('/assets/terrain_height.jpg');
    const normal = loader.load('/assets/terrain_normal.jpg');

    diffuse.colorSpace = THREE.SRGBColorSpace;
    diffuse.wrapS = diffuse.wrapT = THREE.ClampToEdgeWrapping;
    height.wrapS = height.wrapT = THREE.ClampToEdgeWrapping;
    normal.wrapS = normal.wrapT = THREE.ClampToEdgeWrapping;

    // Photorealistic Himalayan Digital Elevation Model
    const terrainGeo = new THREE.PlaneGeometry(terrainSize, terrainSize, segments, segments);
    terrainGeo.rotateX(-Math.PI / 2);

    const terrainMat = new THREE.MeshStandardMaterial({
      map: diffuse,
      displacementMap: height,
      displacementScale: 14.0,
      displacementBias: -2.0,
      normalMap: normal,
      normalScale: new THREE.Vector2(1.2, 1.2),
      roughness: 0.85,
      metalness: 0.06,
      wireframe: false
    });

    this.terrainMesh = new THREE.Mesh(terrainGeo, terrainMat);
    this.scene.add(this.terrainMesh);

    // Tactical Elevation Contour Grid (Soft top-down topographic lines)
    const contourGeo = new THREE.PlaneGeometry(terrainSize, terrainSize, 80, 80);
    contourGeo.rotateX(-Math.PI / 2);

    const contourMat = new THREE.ShaderMaterial({
      uniforms: {
        uColor: { value: new THREE.Color(0x38bdf8) },
        uTime: { value: 0 }
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        uniform float uTime;
        varying vec2 vUv;
        void main() {
          // Tactical 100m contour grid
          vec2 grid = abs(fract(vUv * 40.0 - 0.5) - 0.5);
          float line = min(grid.x, grid.y);
          float alpha = 1.0 - smoothstep(0.0, 0.025, line);
          
          // Subtle pulse sweep
          float sweep = sin(vUv.y * 20.0 - uTime * 0.8) * 0.5 + 0.5;
          sweep = pow(sweep, 6.0) * 0.3;

          // Radial falloff at borders
          float dist = length(vUv - 0.5);
          float borderFade = 1.0 - smoothstep(0.25, 0.48, dist);

          gl_FragColor = vec4(uColor, (alpha * 0.07 + sweep * 0.04) * borderFade);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    });

    this.contourMesh = new THREE.Mesh(contourGeo, contourMat);
    this.contourMesh.position.y = 8.5;
    this.scene.add(this.contourMesh);

    // Deep Alpine Glacier Water Plane (Reflective obsidian)
    const waterGeo = new THREE.PlaneGeometry(terrainSize, terrainSize);
    waterGeo.rotateX(-Math.PI / 2);
    const waterMat = new THREE.MeshStandardMaterial({
      color: 0x081420,
      roughness: 0.12,
      metalness: 0.85,
      transparent: true,
      opacity: 0.72
    });
    this.waterMesh = new THREE.Mesh(waterGeo, waterMat);
    this.waterMesh.position.y = -1.8;
    this.scene.add(this.waterMesh);
  }

  _buildSentinel2Satellite() {
    this.satelliteGroup = new THREE.Group();

    // 1. Spacecraft Main Body (Cuboid bus wrapped in Golden MLI thermal foil)
    const busGeo = new THREE.BoxGeometry(2.4, 1.6, 1.4);
    const mliMat = new THREE.MeshStandardMaterial({
      color: 0xdfa128,
      metalness: 0.95,
      roughness: 0.22,
      envMapIntensity: 1.5
    });
    const bus = new THREE.Mesh(busGeo, mliMat);
    this.satelliteGroup.add(bus);

    // 2. Multi-Spectral Instrument (MSI) Payload Optical Aperture
    const msiGeo = new THREE.CylinderGeometry(0.5, 0.6, 1.0, 24);
    const msiMat = new THREE.MeshStandardMaterial({
      color: 0x1a1a1f,
      metalness: 0.8,
      roughness: 0.3
    });
    const msi = new THREE.Mesh(msiGeo, msiMat);
    msi.position.y = -0.9;
    this.satelliteGroup.add(msi);

    // Optical primary mirror lens (Cyan AR coated)
    const lensGeo = new THREE.CircleGeometry(0.46, 24);
    lensGeo.rotateX(Math.PI / 2);
    const lensMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      side: THREE.DoubleSide
    });
    const lens = new THREE.Mesh(lensGeo, lensMat);
    lens.position.y = -1.41;
    this.satelliteGroup.add(lens);

    // 3. Photovoltaic Solar Array Wing (Deployable 3-panel single wing, Sentinel-2 design)
    const solarWing = new THREE.Group();
    const panelGeo = new THREE.BoxGeometry(6.5, 0.08, 2.2);
    const solarMat = new THREE.MeshStandardMaterial({
      color: 0x11284a, // Deep blue space-grade silicon cells
      metalness: 0.75,
      roughness: 0.28
    });
    const panel = new THREE.Mesh(panelGeo, solarMat);
    panel.position.x = 4.6;
    solarWing.add(panel);

    // Gold solar panel bracket arm
    const armGeo = new THREE.CylinderGeometry(0.1, 0.1, 1.4, 8);
    armGeo.rotateZ(Math.PI / 2);
    const armMat = new THREE.MeshStandardMaterial({ color: 0xdfa128, metalness: 0.9 });
    const arm = new THREE.Mesh(armGeo, armMat);
    arm.position.x = 1.6;
    solarWing.add(arm);

    this.satelliteGroup.add(solarWing);

    // 4. X-Band Telemetry Antenna Dish
    const dishGeo = new THREE.SphereGeometry(0.4, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2);
    dishGeo.rotateX(-Math.PI / 2);
    const dishMat = new THREE.MeshStandardMaterial({ color: 0xd8d8e2, metalness: 0.85 });
    const dish = new THREE.Mesh(dishGeo, dishMat);
    dish.position.set(-0.8, -0.6, 0.5);
    this.satelliteGroup.add(dish);

    // Orbital trajectory parameters
    this.satelliteAltitude = 38;
    this.satelliteOrbitRadius = 55;
    this.satelliteGroup.position.set(0, this.satelliteAltitude, 0);
    this.scene.add(this.satelliteGroup);

    // 5. Sentinel-2 Orbital Ground Track (Luminescent flight path spline)
    const trackPoints = [];
    const segments = 120;
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      const x = Math.sin(angle) * this.satelliteOrbitRadius;
      const z = Math.cos(angle) * (this.satelliteOrbitRadius * 0.75);
      const y = this.satelliteAltitude + Math.sin(angle * 2) * 4;
      trackPoints.push(new THREE.Vector3(x, y, z));
    }
    const trackGeo = new THREE.BufferGeometry().setFromPoints(trackPoints);
    const trackMat = new THREE.LineDashedMaterial({
      color: 0x38bdf8,
      dashSize: 2,
      gapSize: 1.5,
      transparent: true,
      opacity: 0.35
    });
    this.orbitTrack = new THREE.Line(trackGeo, trackMat);
    this.orbitTrack.computeLineDistances();
    this.scene.add(this.orbitTrack);
  }

  _buildSensorFrustum() {
    // Volumetric Sensor Frustum: 4-sided pyramid from satellite MSI down to ground swath
    const frustumGeo = new THREE.BufferGeometry();

    // 5 vertices: Apex at (0,0,0), and 4 ground corners
    // Ground swath size: 24m x 24m on terrain
    const h = -34;
    const w = 12;
    const d = 12;

    const vertices = new Float32Array([
      // 4 triangular sides
      0, 0, 0,   -w, h, -d,   w, h, -d, // Side 1 (North)
      0, 0, 0,    w, h, -d,   w, h,  d, // Side 2 (East)
      0, 0, 0,    w, h,  d,  -w, h,  d, // Side 3 (South)
      0, 0, 0,   -w, h,  d,  -w, h, -d  // Side 4 (West)
    ]);

    frustumGeo.setAttribute('position', new THREE.BufferAttribute(vertices, 3));

    const frustumMat = new THREE.ShaderMaterial({
      uniforms: {
        uColor: { value: new THREE.Color(0x10b981) }, // Sentinel-2 Emerald laser swath
        uScanY: { value: 0 }
      },
      vertexShader: `
        varying vec3 vPos;
        void main() {
          vPos = position;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        varying vec3 vPos;
        void main() {
          // Gradual vertical transparency: bright at aperture, subtle at ground
          float t = clamp(-vPos.y / 34.0, 0.0, 1.0);
          float alpha = (1.0 - t * 0.7) * 0.14;
          gl_FragColor = vec4(uColor, alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending
    });

    this.sensorFrustum = new THREE.Mesh(frustumGeo, frustumMat);
    this.satelliteGroup.add(this.sensorFrustum);

    // Ground Swath Scanning Laser Reticle
    const swathGeo = new THREE.PlaneGeometry(24, 24);
    swathGeo.rotateX(-Math.PI / 2);
    const swathMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: new THREE.Color(0x38bdf8) }
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        uniform float uTime;
        varying vec2 vUv;
        void main() {
          // Perimeter border
          vec2 b = abs(vUv - 0.5) * 2.0;
          float edge = max(b.x, b.y);
          float border = smoothstep(0.96, 1.0, edge);

          // Sweeping pushbroom scanline
          float scan = sin(vUv.y * 3.14159 - uTime * 3.0);
          float line = smoothstep(0.04, 0.0, abs(scan));

          // Center crosshair
          float chX = smoothstep(0.005, 0.0, abs(vUv.x - 0.5)) * (1.0 - step(0.15, abs(vUv.y - 0.5)));
          float chY = smoothstep(0.005, 0.0, abs(vUv.y - 0.5)) * (1.0 - step(0.15, abs(vUv.x - 0.5)));

          float a = border * 0.6 + line * 0.7 + (chX + chY) * 0.5;
          gl_FragColor = vec4(uColor, a * 0.85);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    });

    this.groundSwath = new THREE.Mesh(swathGeo, swathMat);
    this.groundSwath.position.y = 4.2;
    this.scene.add(this.groundSwath);
  }

  _buildTacticalReticles() {
    this.reticleGroup = new THREE.Group();

    // 3D forward post beacon (Target ALT-2026-0391)
    const beaconGeo = new THREE.CylinderGeometry(0.1, 0.1, 6, 8);
    const beaconMat = new THREE.MeshBasicMaterial({
      color: 0xf43f5e,
      transparent: true,
      opacity: 0.85
    });
    const beacon = new THREE.Mesh(beaconGeo, beaconMat);
    beacon.position.set(-4, 9, 2);
    this.reticleGroup.add(beacon);

    // Concentric tactical targeting rings on the structure coordinate
    const ringGeo = new THREE.RingGeometry(1.2, 1.35, 32);
    ringGeo.rotateX(-Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xf43f5e,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.9
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(-4, 6.2, 2);
    this.reticleGroup.add(ring);

    this.scene.add(this.reticleGroup);
  }

  _initPostProcessing() {
    const POST = window.THREE_POST;
    if (!POST) return;

    this.composer = new POST.EffectComposer(this.renderer);
    const renderPass = new POST.RenderPass(this.scene, this.camera);
    this.composer.addPass(renderPass);

    // UnrealBloomPass: subtle bloom for satellite solar glint and sensor lasers
    this.bloomPass = new POST.UnrealBloomPass(
      new THREE.Vector2(window.innerWidth, window.innerHeight),
      0.45,  // strength (refined, non-glowing)
      0.6,   // radius
      0.82   // threshold (only highlights and lasers bloom)
    );
    this.composer.addPass(this.bloomPass);

    // Tactical Color Grading & Crisp Vignette Pass
    const gradingShader = {
      uniforms: {
        tDiffuse: { value: null }
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform sampler2D tDiffuse;
        varying vec2 vUv;
        void main() {
          vec4 col = texture2D(tDiffuse, vUv);

          // Crisp aerospace optical vignette
          vec2 d = (vUv - 0.5) * 1.35;
          float vig = clamp(1.0 - dot(d, d) * 0.65, 0.0, 1.0);
          col.rgb *= vig;

          // Pure black floor preservation (SpaceX standard)
          col.rgb = max(vec3(0.0), col.rgb);

          gl_FragColor = col;
        }
      `
    };

    const gradingPass = new POST.ShaderPass(gradingShader);
    this.composer.addPass(gradingPass);
  }

  _initControls() {
    this.cameraPreset = 'ORBIT';

    const handleDown = (e) => {
      this.isMouseDown = true;
      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    };

    const handleWheel = (e) => {
      e.preventDefault();
      this.spherical.radius = Math.max(22, Math.min(140, this.spherical.radius + e.deltaY * 0.04));
      if (this.cameraPreset === 'SATELLITE') this.cameraPreset = 'ORBIT';
      this._updateSphericalPosition();
    };

    // Primary canvas listeners
    this.canvas.addEventListener('mousedown', handleDown);
    this.canvas.addEventListener('wheel', handleWheel, { passive: false });

    // Also forward mouse interaction from the map container when in 3D mode
    const mapContainer = document.querySelector('.map-canvas-container');
    if (mapContainer) {
      mapContainer.addEventListener('mousedown', (e) => {
        if (mapContainer.classList.contains('mode-3d-active')) {
          handleDown(e);
        }
      });
      mapContainer.addEventListener('wheel', (e) => {
        if (mapContainer.classList.contains('mode-3d-active')) {
          handleWheel(e);
        }
      }, { passive: false });
    }

    window.addEventListener('mouseup', () => {
      this.isMouseDown = false;
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isMouseDown) return;

      const deltaX = e.clientX - this.previousMousePosition.x;
      const deltaY = e.clientY - this.previousMousePosition.y;

      if (this.cameraPreset === 'SATELLITE') this.cameraPreset = 'ORBIT';

      this.spherical.theta -= deltaX * 0.005;
      this.spherical.phi = Math.max(0.12, Math.min(Math.PI / 2.05, this.spherical.phi - deltaY * 0.005));

      this._updateSphericalPosition();

      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('resize', () => this._onResize());
  }

  setCameraPreset(preset) {
    this.cameraPreset = preset;
    if (preset === 'ORTHO') {
      // Direct Nadir Reconnaissance Pass (looking straight down)
      this.spherical.radius = 56;
      this.spherical.phi = 0.05;
      this.spherical.theta = 0.0;
      this._updateSphericalPosition();
    } else if (preset === 'OBLIQUE') {
      // 35° Low-Glance Mountain Terrain Horizon
      this.spherical.radius = 48;
      this.spherical.phi = Math.PI / 2.25;
      this.spherical.theta = -0.55;
      this._updateSphericalPosition();
    } else if (preset === 'ORBIT') {
      // Standard Tactical 45° Orbit
      this.spherical.radius = 62;
      this.spherical.phi = Math.PI / 3.4;
      this.spherical.theta = 0.15;
      this._updateSphericalPosition();
    }
  }

  _updateSphericalPosition() {
    const { radius, phi, theta } = this.spherical;
    this.desiredPos.x = this.cameraTarget.x + radius * Math.sin(phi) * Math.sin(theta);
    this.desiredPos.y = this.cameraTarget.y + radius * Math.cos(phi);
    this.desiredPos.z = this.cameraTarget.z + radius * Math.sin(phi) * Math.cos(theta);
  }

  _onResize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    if (this.composer) this.composer.setSize(w, h);
  }

  /**
   * Smooth Cinematic Tactical Flyover to target sector
   */
  flyToSector(aoiId) {
    const wp = this.sectorWaypoints[aoiId];
    if (!wp) return;

    this.activeAoi = aoiId;
    this.desiredTarget.copy(wp.target);

    // Compute spherical coordinates relative to new target
    const offset = wp.camOffset;
    this.spherical.radius = offset.length();
    this.spherical.phi = Math.acos(offset.y / this.spherical.radius);
    this.spherical.theta = Math.atan2(offset.x, offset.z);

    this._updateSphericalPosition();

    // Reposition ground swath to active sector target
    if (this.groundSwath) {
      this.groundSwath.position.x = wp.target.x;
      this.groundSwath.position.z = wp.target.z;
    }
  }

  _animate() {
    requestAnimationFrame(() => this._animate());
    if (!this.ready) return;

    const delta = this.clock.getDelta();
    const elapsed = this.clock.getElapsedTime();

    // Animate Sentinel-2 Orbit
    if (this.satelliteGroup) {
      const orbitSpeed = 0.06;
      const angle = elapsed * orbitSpeed;
      const sx = Math.sin(angle) * this.satelliteOrbitRadius;
      const sz = Math.cos(angle) * (this.satelliteOrbitRadius * 0.75);
      const sy = this.satelliteAltitude + Math.sin(angle * 2) * 2.5;

      this.satelliteGroup.position.set(sx, sy, sz);

      // Aim satellite MSI aperture directly at the ground target
      this.satelliteGroup.lookAt(this.cameraTarget.x, 0, this.cameraTarget.z);

      // Satellite Chase Cam mode
      if (this.cameraPreset === 'SATELLITE') {
        const chasePos = new THREE.Vector3(sx * 1.15, sy + 6, sz * 1.15);
        this.desiredPos.copy(chasePos);
        this.desiredTarget.set(this.cameraTarget.x, 2, this.cameraTarget.z);
      }
    }

    // Smooth camera interpolation
    this.camera.position.lerp(this.desiredPos, 0.045);
    this.cameraTarget.lerp(this.desiredTarget, 0.045);
    this.camera.lookAt(this.cameraTarget);

    // Update scanline shaders
    if (this.contourMesh && this.contourMesh.material.uniforms) {
      this.contourMesh.material.uniforms.uTime.value = elapsed;
    }

    if (this.groundSwath && this.groundSwath.material.uniforms) {
      this.groundSwath.material.uniforms.uTime.value = elapsed;
    }

    // Render
    if (this.composer) {
      this.composer.render();
    } else {
      this.renderer.render(this.scene, this.camera);
    }
  }
}

// Export singleton globally
window.SentryEnvironment = SentryEnvironment;
