class AdvancedAvatarAnimator {
    constructor(avatar, scene, camera) {
        this.avatar = avatar;
        this.scene = scene;
        this.camera = camera;
        
        this.isAnimating = false;
        this.eyeAnimationActive = false;
        this.bodyAnimationActive = false;
        this.facialAnimationActive = false;
        
        this.bones = {};
        this.meshes = {};
        this.morphTargets = {};
        
        this.naturalParams = {
            blinkFrequency: 3000,
            eyeMovementFrequency: 2000,
            gestureFrequency: 8000,
            headMovementFrequency: 15000,
            breathingRate: 4000,
            idleMovementFrequency: 6000,
        };
        
        this.intensities = {
            breathing: 0.015,
            eyeMovement: 0.3,
            headMovement: 0.1,
            gestureMovement: 0.2,
            faceExpression: 0.4,
            posture: 0.05
        };
        
        this.initializeAvatarStructure();
        this.startAllAnimations();
    }

    initializeAvatarStructure() {
        if (!this.avatar) return;
        
        
        this.avatar.traverse((child) => {
            if (child.isBone || child.type === 'Bone') {
                const boneName = child.name.toLowerCase();
                this.bones[boneName] = child;
                
                if (boneName.includes('head')) this.bones.head = child;
                if (boneName.includes('neck')) this.bones.neck = child;
                if (boneName.includes('spine')) this.bones.spine = child;
                if (boneName.includes('chest')) this.bones.chest = child;
                if (boneName.includes('leftarm') || boneName.includes('left_arm')) this.bones.leftArm = child;
                if (boneName.includes('rightarm') || boneName.includes('right_arm')) this.bones.rightArm = child;
                if (boneName.includes('lefthand') || boneName.includes('left_hand')) this.bones.leftHand = child;
                if (boneName.includes('righthand') || boneName.includes('right_hand')) this.bones.rightHand = child;
                if (boneName.includes('leftleg') || boneName.includes('left_leg')) this.bones.leftLeg = child;
                if (boneName.includes('rightleg') || boneName.includes('right_leg')) this.bones.rightLeg = child;
                if (boneName.includes('hips') || boneName.includes('pelvis')) this.bones.hips = child;
            }
            
            if (child.isMesh) {
                this.meshes[child.name] = child;
                
                if (child.morphTargetDictionary) {
                    this.morphTargets[child.name] = {
                        mesh: child,
                        dictionary: child.morphTargetDictionary,
                        influences: child.morphTargetInfluences
                    };
                }
            }
        });

        console.log('avatar make', {
            bones: Object.keys(this.bones).length,
            meshes: Object.keys(this.meshes).length,
            morphTargets: Object.keys(this.morphTargets).length
        });
        
        if (!this._scanDone) {
        this._scanDone = true;
        this._facialReport = this.scanFacialMorphs(this.avatar);
        }

    }

    scanFacialMorphs(root ) {
    const blinkPatterns = [
        /^(eye)?blink(left|right)?$/i,
        /^eyes?Closed$/i,
        /^eyeClose(left|right)?$/i,
        /^eyeLid(Upper|Lower)(Left|Right)?$/i,
        /^eyesLook(Up|Down)$/i,    
        /^Blink_L$/i, /^Blink_R$/i, 
    ];
    const mouthPatterns = [/^mouthOpen$/i, /^jawOpen$/i];
    const smilePatterns = [/^mouthSmile(left|right)?$/i, /^smile(left|right)?$/i];
    const browPatterns  = [/^brow(InnerUp|OuterUp|Down)(Left|Right)?$/i];

    const found = {
        blink: [], mouth: [], smile: [], brow: [],
        totalMeshes: 0, meshesWithMorphs: 0
    };

    const matchKeys = (dict, patterns) => {
        const hits = [];
        const entries = Object.entries(dict); 
        for (const [name, idx] of entries) {
        if (patterns.some(rx => rx.test(name))) hits.push({ name, idx });
        }
        return hits;
    };

    root.traverse((child) => {
        if (!child.isMesh) return;
        found.totalMeshes++;

        const dict = child.morphTargetDictionary;
        const infl = child.morphTargetInfluences;
        if (!dict || !infl) {
        return;
        }
        found.meshesWithMorphs++;

        const blinkHits = matchKeys(dict, blinkPatterns);
        const mouthHits = matchKeys(dict, mouthPatterns);
        const smileHits = matchKeys(dict, smilePatterns);
        const browHits  = matchKeys(dict, browPatterns);

        if (blinkHits.length) {
        found.blink.push({ mesh: child.name, hits: blinkHits });
        } 
        if (mouthHits.length) {
        found.mouth.push({ mesh: child.name, hits: mouthHits });
        }
        if (smileHits.length) {
        found.smile.push({ mesh: child.name, hits: smileHits });
        }
        if (browHits.length) {
        found.brow.push({ mesh: child.name, hits: browHits });
        }
        console.groupEnd();
    });

    const hasBlink = found.blink.length > 0;
    if (hasBlink) {
        found.blink.forEach(entry => {
        entry.hits.forEach(h => {
            console.log(`   • "${h.name}"  mesh "${entry.mesh}" (index ${h.idx})`);
        });
        });
    } 

    return { hasBlink, found };
    }


    startAllAnimations() {
        this.isAnimating = true;
        this.eyeAnimationActive = true;
        this.bodyAnimationActive = true;
        this.facialAnimationActive = true;
        
        this.startMainAnimationLoop();
        this.startAdvancedEyeAnimation();
        this.startNaturalFacialExpressions();
        this.startBodyLanguageAnimation();
        this.startSubtleIdleMovements();
        this.maintainDirectGaze();
        
    }

    startMainAnimationLoop() {
        const clock = new THREE.Clock();
        
        const animate = () => {
            if (!this.isAnimating) return;
            
            const time = clock.getElapsedTime();
            
            this.animateNaturalBreathing(time);
            
            this.animateSubtleBodyMovements(time);
            
            requestAnimationFrame(animate);
        };
        
        animate();
    }

    startAdvancedEyeAnimation() {
        const animateEyes = () => {
            if (!this.eyeAnimationActive) return;
            
            this.animateNaturalBlink();
            this.animateNaturalEyeMovement();
            
            setTimeout(animateEyes, 50);
        };
        
        animateEyes();
    }

    startNaturalFacialExpressions() {
        const animateFace = () => {
            if (!this.facialAnimationActive) return;
            
            this.animateSubtleFacialChanges();
            this.animateEyebrowMovements();
            
            setTimeout(animateFace, 100);
        };
        
        animateFace();
    }

    startBodyLanguageAnimation() {
        const animateBody = () => {
            if (!this.bodyAnimationActive) return;
            
            this.animateNaturalHandGestures();
            this.animateShoulderMovements();
            
            setTimeout(animateBody, 150);
        };
        
        animateBody();
    }

    startSubtleIdleMovements() {
        const animateIdle = () => {
            if (!this.isAnimating) return;
            
            this.animateWeightShift();
            this.animateIdleHeadMovements();
            
            setTimeout(animateIdle, 200);
        };
        
        animateIdle();
    }

    maintainDirectGaze() {
        const lookAtCamera = () => {
            if (!this.avatar || !this.camera) return;
            
            if (this.bones.head) {
                this.bones.head.lookAt(this.camera.position);
            } else {
                this.avatar.lookAt(this.camera.position);
            }
            
            requestAnimationFrame(lookAtCamera);
        };
        lookAtCamera();
    }

    animateNaturalBlink() {
        if (Math.random() < 0.02) {
            Object.values(this.morphTargets).forEach(meshData => {
                const blinkTargets = ['eyeBlinkLeft', 'eyeBlinkRight', 'blink', 'eyesClosed'];
                blinkTargets.forEach(target => {
                    if (meshData.dictionary[target] !== undefined) {
                        const idx = meshData.dictionary[target];
                        meshData.influences[idx] = 1;
                        setTimeout(() => meshData.influences[idx] = 0, 100);
                    }
                });
            });
        }
    }

    animateNaturalEyeMovement() {
        if (Math.random() < 0.01) {
            Object.values(this.morphTargets).forEach(meshData => {
                const eyeTargets = ['eyeLookLeft', 'eyeLookRight', 'eyeLookUp', 'eyeLookDown'];
                eyeTargets.forEach(target => {
                    if (meshData.dictionary[target] !== undefined) {
                        const idx = meshData.dictionary[target];
                        meshData.influences[idx] = (Math.random() - 0.5) * 0.3;
                        setTimeout(() => meshData.influences[idx] = 0, 1000);
                    }
                });
            });
        }
    }

    animateSubtleFacialChanges() {
        if (Math.random() < 0.01) {
            Object.values(this.morphTargets).forEach(meshData => {
                const faceTargets = ['mouthSmile', 'mouthFrown', 'cheekPuff'];
                faceTargets.forEach(target => {
                    if (meshData.dictionary[target] !== undefined) {
                        const idx = meshData.dictionary[target];
                        meshData.influences[idx] = Math.random() * 0.2;
                        setTimeout(() => meshData.influences[idx] = 0, 2000);
                    }
                });
            });
        }
    }

    animateEyebrowMovements() {
        if (Math.random() < 0.01) {
            Object.values(this.morphTargets).forEach(meshData => {
                const browTargets = ['browInnerUp', 'browDownLeft', 'browDownRight'];
                browTargets.forEach(target => {
                    if (meshData.dictionary[target] !== undefined) {
                        const idx = meshData.dictionary[target];
                        meshData.influences[idx] = (Math.random() - 0.5) * 0.3;
                        setTimeout(() => meshData.influences[idx] = 0, 1500);
                    }
                });
            });
        }
    }

    animateNaturalHandGestures() {
        const hands = [this.bones.leftHand, this.bones.rightHand, this.bones.leftArm, this.bones.rightArm];
        hands.forEach(hand => {
            if (hand && Math.random() < 0.005) {
                const originalRotation = hand.rotation.clone();
                hand.rotation.x += (Math.random() - 0.5) * 0.1;
                hand.rotation.y += (Math.random() - 0.5) * 0.1;
                hand.rotation.z += (Math.random() - 0.5) * 0.1;
                setTimeout(() => hand.rotation.copy(originalRotation), 2000);
            }
        });
    }

    animateShoulderMovements() {
        const shoulders = [this.bones.leftArm, this.bones.rightArm];
        shoulders.forEach(shoulder => {
            if (shoulder && Math.random() < 0.003) {
                const originalRotation = shoulder.rotation.clone();
                shoulder.rotation.z += (Math.random() - 0.5) * 0.05;
                setTimeout(() => shoulder.rotation.copy(originalRotation), 3000);
            }
        });
    }

    animateIdleHeadMovements() {
        if (this.bones.head && Math.random() < 0.008) {
            const originalRotation = this.bones.head.rotation.clone();
            this.bones.head.rotation.y += (Math.random() - 0.5) * 0.08;
            this.bones.head.rotation.x += (Math.random() - 0.5) * 0.04;
            setTimeout(() => this.bones.head.rotation.copy(originalRotation), 1500);
        }
    }

    animateWeightShift() {
        if (this.bones.hips) {
            this.bones.hips.position.x = Math.sin(Date.now() * 0.0008) * 0.02;
            this.bones.hips.position.z = Math.cos(Date.now() * 0.0005) * 0.01;
        }
    }

    animateNaturalBreathing(time) {
        if (this.bones.chest) {
            this.bones.chest.scale.y = 1 + Math.sin(time * 0.5) * this.intensities.breathing;
            this.bones.chest.scale.x = 1 + Math.sin(time * 0.5) * (this.intensities.breathing * 0.5);
        }
        
        if (this.bones.spine) {
            this.bones.spine.rotation.x = Math.sin(time * 0.5) * 0.01;
        }
    }

    animateSubtleBodyMovements(time) {
        if (this.bones.leftLeg && this.bones.rightLeg) {
            this.bones.leftLeg.rotation.x = Math.sin(time * 0.3) * 0.02;
            this.bones.rightLeg.rotation.x = Math.sin(time * 0.3 + Math.PI) * 0.02;
        }
        
        if (this.avatar) {
            this.avatar.position.y = Math.sin(time * 1.2) * 0.008 - 1.5;
            this.avatar.rotation.y = Math.sin(time * 0.1) * 0.005;
        }
    }

    stopAllAnimations() {
        this.isAnimating = false;
        this.eyeAnimationActive = false;
        this.bodyAnimationActive = false;
        this.facialAnimationActive = false;
    }

    resumeAllAnimations() {
        this.startAllAnimations();
    }
}

class VoiceAssistant {
    constructor() {
        this.isRecording = false;
        this.isHolding = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.avatar = null;
        this.mixer = null;
        this.currentEmotion = 'Neutral';
        this.isPlaying = false;
        this.currentAudio = null;
        this.conversationHistory = [];
        this.voiceStream = null;
        this.recordingStartTime = null;
        this.backgroundRotationSpeed = 0.002;
        this.useCustomVoice = true; 
        this.sessionId = null;
        this.hasDepressionResults = false;
        
        this.audioContext = null;
        this.eyeAnimationActive = false;
        this.bodyAnimationActive = false;
        
        this.phonemeToViseme = {
            'A': 'mouthOpen',
            'E': 'mouthSmile', 
            'I': 'mouthSmile',
            'O': 'mouthO',
            'U': 'mouthO',
            
            'M': 'mouthClosed',
            'B': 'mouthClosed', 
            'P': 'mouthClosed',
            'F': 'mouthLowerLip',
            'V': 'mouthLowerLip',
            'TH': 'mouthOpen',
            'S': 'mouthSmile',
            'SH': 'mouthO',
            'CH': 'mouthO',
            'L': 'mouthOpen',
            'R': 'mouthO'
        };

        this.initializeApp();
    }
    loadSavedSettings() {
        try {
            const savedVoiceType = localStorage.getItem('voiceType') || 'fast';
            this.useCustomVoice = savedVoiceType === 'custom';
            console.log(`Loaded voice type: ${savedVoiceType}, useCustomVoice: ${this.useCustomVoice}`);
        } catch (error) {
            console.warn('Error loading settings:', error);
            this.useCustomVoice = false;
        }
    }

    setMouthOpen(amount, emotion = 'neutral') {
        if (!this.mouthMesh || this.jawOpenIndex === null) return;
        
        try {
            if (this.mouthMesh.morphTargetInfluences && 
                this.mouthMesh.morphTargetInfluences[this.jawOpenIndex] !== undefined) {
                this.mouthMesh.morphTargetInfluences[this.jawOpenIndex] = 
                    Math.max(0, Math.min(1, amount));
            }
        } catch (error) {
            console.warn('Error setting mouth open:', error);
        }
    }

    showNotification(message, duration = 3000) {
        
        const notification = document.createElement('div');
        notification.className = 'voice-notification';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(124, 77, 255, 0.9);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 1000;
            font-size: 14px;
            opacity: 0;
            transition: opacity 0.3s ease;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => notification.style.opacity = '1', 100);
        
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, duration);
    }

    async initializeApp() {
        await this.waitForDOM();

        const urlParams = new URLSearchParams(window.location.search);
        this.sessionId = urlParams.get('session_id');

        this.loadSavedSettings();

        this.setupEventListeners();

        setTimeout(() => {
            this.updateVoiceTypeUI();
        }, 100);

        await this.initializeThreeJS();
        await this.loadAvatar();
        this.startRenderLoop();
        this.createParticleEffects();
        this.autoResizeTextarea();

    }



    async generateInitialMessage() {
        try {
            const response = await fetch('/generate-initial-message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId
                })
            });

            const data = await response.json();
            
            if (data.success) {
                this.hasDepressionResults = data.hasDepressionContext;
                
                setTimeout(() => {
                    this.displayMessage(data.message, 'ai');
                }, 1000);
            } else {
                setTimeout(() => {
                    this.displayMessage("Welcome! I'm Dr. Alfred Adler. I'm here to provide you with psychological support and guidance. What brings you to our session today?", 'ai');
                }, 1000);
            }
        } catch (error) {
            console.error('Error generating initial message:', error);
            setTimeout(() => {
                this.displayMessage("Welcome! I'm Dr. Alfred Adler. How can I help you today?", 'ai');
            }, 1000);
        }
    }

    async waitForDOM() {
        return new Promise((resolve) => {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', resolve);
            } else {
                resolve();
            }
        });
    }

    setupEventListeners() {
        const elements = {
            voiceBtn: document.getElementById('voice-btn'),
            sendBtn: document.getElementById('send-btn'),
            messageInput: document.getElementById('message-input'),
            imageInput: document.getElementById('image-input'),
            themeToggle: document.getElementById('theme-toggle'),
            stopBtn: document.getElementById('stop-btn'),
            regenerateBtn: document.getElementById('regenerate-btn'),
            exportBtn: document.getElementById('export-btn'),
            voiceTypeToggle: document.getElementById('voice-type-toggle') 
        };

        Object.keys(elements).forEach(key => {
            if (!elements[key] && key !== 'voiceTypeToggle') { 
                console.error(`Element ${key} not found`);
                return;
            }
        });

        if (elements.voiceBtn) {
            elements.voiceBtn.addEventListener('mousedown', (e) => {
                e.preventDefault();
                this.startHoldToSpeak();
            });

            elements.voiceBtn.addEventListener('mouseup', (e) => {
                e.preventDefault();
                this.endHoldToSpeak();
            });

            elements.voiceBtn.addEventListener('mouseleave', (e) => {
                e.preventDefault();
                if (this.isHolding) this.endHoldToSpeak();
            });

            elements.voiceBtn.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.startHoldToSpeak();
            });

            elements.voiceBtn.addEventListener('touchend', (e) => {
                e.preventDefault();
                this.endHoldToSpeak();
            });
        }

        if (elements.sendBtn) {
            elements.sendBtn.addEventListener('click', () => this.sendMessage());
        }

        if (elements.messageInput) {
            elements.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        if (elements.themeToggle) {
            elements.themeToggle.addEventListener('click', () => this.toggleTheme());
        }

        if (elements.stopBtn) {
            elements.stopBtn.addEventListener('click', () => this.stopPlayback());
        }

        if (elements.regenerateBtn) {
            elements.regenerateBtn.addEventListener('click', () => this.regenerateResponse());
        }

        if (elements.exportBtn) {
            elements.exportBtn.addEventListener('click', () => this.exportSession());
        }

        if (elements.voiceTypeToggle) {
            console.log('Voice type toggle button found, adding event listener');
            elements.voiceTypeToggle.addEventListener('click', () => {
                console.log('Voice type toggle button clicked');
                this.toggleVoiceType();
            });
        } else {
            console.error('Voice type toggle button not found in DOM');
        }


        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isRecording) {
                this.endHoldToSpeak();
            }
            
            if (e.ctrlKey && e.key === 'v') {
                e.preventDefault();
                this.toggleVoiceType();
            }
        });

    }

    toggleVoiceType() {        
        this.useCustomVoice = !this.useCustomVoice;
        this.updateVoiceTypeUI();
        const voiceType = this.useCustomVoice ? 'Custom Voice (Personalized)' : 'Fast Voice (Edge TTS)';
        this.showNotification(` Switched to ${voiceType}`);

        try {
            localStorage.setItem('voiceType', this.useCustomVoice ? 'custom' : 'fast');
        } catch (error) {
            console.error('Error saving voice type:', error);
        }
    }


    updateVoiceTypeUI() {
        const voiceTypeBtn = document.getElementById('voice-type-toggle');
        if (!voiceTypeBtn) {
            console.log('Voice type button not found');
            return;
        }
        
        const voiceTypeText = voiceTypeBtn.querySelector('.voice-type-text');
        const voiceTypeIcon = voiceTypeBtn.querySelector('i');

        voiceTypeBtn.classList.remove('custom-voice', 'fast-voice');

        if (this.useCustomVoice) {
            voiceTypeBtn.classList.add('custom-voice');
            if (voiceTypeText) voiceTypeText.textContent = 'Custom Voice';
            if (voiceTypeIcon) voiceTypeIcon.className = 'fas fa-user-tie';
            voiceTypeBtn.title = 'Switch to Fast Voice (Edge TTS)';
            console.log('UI updated to Custom Voice');
        } else {
            voiceTypeBtn.classList.add('fast-voice');
            if (voiceTypeText) voiceTypeText.textContent = 'Fast Voice';
            if (voiceTypeIcon) voiceTypeIcon.className = 'fas fa-bolt';
            voiceTypeBtn.title = 'Switch to Custom Voice (Personalized)';
            console.log('UI updated to Fast Voice');
        }
    }



    showVoiceTypeIndicator(voiceType) {
        const avatarContainer = document.querySelector('.avatar-container');
        if (!avatarContainer) return;

        const existingIndicator = avatarContainer.querySelector('.voice-type-indicator');
        if (existingIndicator) {
            existingIndicator.remove();
        }

        const indicator = document.createElement('div');
        indicator.className = 'voice-type-indicator';
        indicator.innerHTML = `<i class="fas ${voiceType.includes('Custom') ? 'fa-user-tie' : 'fa-bolt'}"></i> ${voiceType}`;
        
        indicator.style.cssText = `
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 12px;
            z-index: 10;
            opacity: 0;
            transition: opacity 0.3s ease;
        `;

        avatarContainer.appendChild(indicator);

        setTimeout(() => {
            indicator.style.opacity = '1';
        }, 100);

        setTimeout(() => {
            indicator.style.opacity = '0';
            setTimeout(() => {
                if (indicator.parentNode) {
                    indicator.parentNode.removeChild(indicator);
                }
            }, 300);
        }, 3000);
    }

    async initializeThreeJS() {
        const canvas = document.getElementById('avatar-canvas');
        if (!canvas) {
            console.error('Avatar canvas not found');
            return;
        }
        
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(50, canvas.offsetWidth / canvas.offsetHeight, 0.1, 1000);
        this.renderer = new THREE.WebGLRenderer({ 
            canvas, 
            alpha: true, 
            antialias: true,
            powerPreference: 'high-performance'
        });
        
        this.renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.3;
        
        if (typeof THREE.OrbitControls !== 'undefined') {
            this.controls = new THREE.OrbitControls(this.camera, canvas);
            this.controls.enableDamping = true;
            this.controls.dampingFactor = 0.05;
            this.controls.enableZoom = true;
            this.controls.enablePan = true;
            this.controls.autoRotate = false;
            this.controls.minPolarAngle = Math.PI / 2.5;
            this.controls.maxPolarAngle = Math.PI / 1.5;
        }
        
        await this.loadEnvironment();
        this.setupLighting();
        
        this.camera.position.set(0, 0, 7);
        this.camera.lookAt(0, 0, 5);
        
        window.addEventListener('resize', () => this.handleResize());
    }

    async loadEnvironment() {
        try {
            if (typeof THREE.EXRLoader !== 'undefined') {
                const exrLoader = new THREE.EXRLoader();
                const exrTexture = await new Promise((resolve, reject) => {
                    exrLoader.load(
                        '/static/assets/DayEnvironmentHDRI069_4K-HDR.exr',
                        resolve,
                        (progress) => console.log('HDRI loading:', (progress.loaded / progress.total * 100) + '%'),
                        reject
                    );
                });
                
                exrTexture.mapping = THREE.EquirectangularReflectionMapping;
                this.scene.environment = exrTexture;
                this.scene.background = exrTexture;
                console.log('HDRI environment loaded successfully');
                
            } else if (typeof THREE.RGBELoader !== 'undefined') {
                const rgbeLoader = new THREE.RGBELoader();
                const hdrTexture = await new Promise((resolve, reject) => {
                    rgbeLoader.load(
                        '/static/assets/DayEnvironmentHDRI069_4K-HDR.exr',
                        resolve,
                        (progress) => console.log('HDRI loading:', (progress.loaded / progress.total * 100) + '%'),
                        reject
                    );
                });
                
                hdrTexture.mapping = THREE.EquirectangularReflectionMapping;
                this.scene.environment = hdrTexture;
                this.scene.background = hdrTexture;
                console.log('HDRI environment loaded successfully');
                
            } else {
                console.warn('EXR/RGBE Loader not available, using fallback');
                this.createFallbackEnvironment();
            }
            
        } catch (error) {
            console.warn('HDRI loading failed, using fallback:', error);
            this.createFallbackEnvironment();
        }
    }

    createFallbackEnvironment() {
        const gradientCanvas = document.createElement('canvas');
        gradientCanvas.width = 1024;
        gradientCanvas.height = 512;
        const ctx = gradientCanvas.getContext('2d');
        
        const gradient = ctx.createLinearGradient(0, 0, 0, 512);
        gradient.addColorStop(0, '#7c4dff');
        gradient.addColorStop(0.5, '#667eea');
        gradient.addColorStop(1, '#764ba2');
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 1024, 512);
        
        const texture = new THREE.CanvasTexture(gradientCanvas);
        texture.mapping = THREE.EquirectangularReflectionMapping;
        this.scene.background = texture;
        this.scene.environment = texture;
    }

    setupLighting() {
        const mainLight = new THREE.DirectionalLight(0xffffff, 2.5);
        mainLight.position.set(5, 10, 5);
        mainLight.castShadow = true;
        this.scene.add(mainLight);

        const fillLight = new THREE.DirectionalLight(0xffffff, 1.2);
        fillLight.position.set(-5, 5, -5);
        this.scene.add(fillLight);

        const ambientLight = new THREE.AmbientLight(0x404040, 1.5);
        this.scene.add(ambientLight);

        const avatarLight = new THREE.SpotLight(0xffffff, 2);
        avatarLight.position.set(0, 8, 8);
        avatarLight.target.position.set(0, 0, 0);
        avatarLight.angle = Math.PI / 3;
        this.scene.add(avatarLight);
        this.scene.add(avatarLight.target);
    }

    async loadAvatar() {
        try {
            if (typeof THREE.GLTFLoader === 'undefined') {
                console.warn('GLTF Loader not available, using fallback avatar');
                this.createFallbackAvatar();
                return;
            }

            const loader = new THREE.GLTFLoader();

            if (typeof THREE.DRACOLoader !== 'undefined') {
                const dracoLoader = new THREE.DRACOLoader();
                dracoLoader.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
                loader.setDRACOLoader(dracoLoader);
            }

            const gltf = await new Promise((resolve, reject) => {
                loader.load(
                    '/static/assets/Alfred_Adler.glb',
                    resolve,
                    (progress) => console.log('Avatar loading:', (progress.loaded / progress.total * 100) + '%'),
                    reject
                );
            });

            this.avatar = gltf.scene;
            this.avatar.scale.setScalar(2);
            this.avatar.position.set(0, -1.5, 0);

            this.avatar.traverse((child) => {
                if (child.isMesh) {
                    child.castShadow = true;
                    child.receiveShadow = true;

                    if (child.material) {
                        child.material.metalness = 0.1;
                        child.material.roughness = 0.8;

                        if (child.material.color) {
                            child.material.color.multiplyScalar(1.5);
                        }

                        child.material.needsUpdate = true;
                        child.material.envMapIntensity = 1.2;
                    }
                }
            });

            this.scene.add(this.avatar);


            this.mouthMesh = null;
            this.jawOpenIndex = null;
            let foundAnyMorphTarget = false;
            let totalMeshes = 0;

            this.avatar.traverse((child) => {
                if (child.isMesh) {
                    totalMeshes++;
                    
                    if (child.morphTargetDictionary) {
                        foundAnyMorphTarget = true;
                        const targets = Object.keys(child.morphTargetDictionary);
                        
                        const mouthKeys = ['jawOpen', 'JawOpen', 'jaw_open', 'mouthOpen', 'mouth_open'];
                        for (const key of mouthKeys) {
                            if (child.morphTargetDictionary[key] !== undefined) {
                                this.mouthMesh = child;
                                this.jawOpenIndex = child.morphTargetDictionary[key];
                                break;
                            }
                        }
                    } 
                }
            });


         

            if (gltf.animations && gltf.animations.length) {
                this.mixer = new THREE.AnimationMixer(this.avatar);
                const idleAction = this.mixer.clipAction(gltf.animations[0]);
                idleAction.play();
            }

            this.advancedAnimator = new AdvancedAvatarAnimator(this.avatar, this.scene, this.camera);

        } catch (error) {
            console.warn('Avatar model loading failed, using fallback:', error);
            this.createFallbackAvatar();
        }
    }

    createFallbackAvatar() {
        const geometry = new THREE.SphereGeometry(1, 64, 32);
        const material = new THREE.MeshStandardMaterial({ 
            color: 0x7c4dff,
            metalness: 0.3,
            roughness: 0.4,
            envMapIntensity: 1
        });
        
        this.avatar = new THREE.Mesh(geometry, material);
        this.avatar.position.set(0, 0, 0);
        this.avatar.castShadow = true;
        this.avatar.receiveShadow = true;
        this.scene.add(this.avatar);
        
        this.advancedAnimator = new AdvancedAvatarAnimator(this.avatar, this.scene, this.camera);

    }

    startRenderLoop() {
        const clock = new THREE.Clock();

        const animate = () => {
            requestAnimationFrame(animate);

            const delta = clock.getDelta();

            if (this.mixer) {
                this.mixer.update(delta);
            }

            if (this.controls) {
                this.controls.update();
            }

            if (this.scene && this.scene.background && this.scene.background.isTexture) {
                this.scene.background.rotation = this.scene.background.rotation || { y: 0 };
                this.scene.background.rotation.y += this.backgroundRotationSpeed;
            }

            if (this.scene && this.scene.environment && this.scene.environment.isTexture) {
                this.scene.environment.rotation = this.scene.environment.rotation || { y: 0 };
                this.scene.environment.rotation.y += this.backgroundRotationSpeed;
            }

            if (this.renderer && this.scene && this.camera) {
                this.renderer.render(this.scene, this.camera);
            }
        };

        animate();
    }


    createParticleEffects() {
        const canvas = document.getElementById('avatar-canvas');
        if (!canvas) return;
        
        const container = canvas.parentElement;
        if (!container) return;
        
        for (let i = 0; i < 6; i++) {
            setTimeout(() => {
                const particle = document.createElement('div');
                particle.className = 'particle';
                particle.style.left = Math.random() * 100 + '%';
                particle.style.animationDelay = Math.random() * 3 + 's';
                particle.style.animationDuration = (3 + Math.random() * 2) + 's';
                container.appendChild(particle);
                
                setTimeout(() => {
                    if (particle.parentNode) {
                        particle.parentNode.removeChild(particle);
                    }
                }, 5000);
            }, i * 300);
        }
        
        setTimeout(() => this.createParticleEffects(), 4000);
    }

    async startHoldToSpeak() {
        if (this.isHolding) return;
        
        try {
            this.voiceStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                } 
            });
            
            this.mediaRecorder = new MediaRecorder(this.voiceStream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            
            this.audioChunks = [];
            this.isHolding = true;
            this.isRecording = true;
            this.recordingStartTime = Date.now();
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };
            
            this.mediaRecorder.onstop = async () => {
                if (this.audioChunks.length > 0) {
                    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                    await this.processVoiceMessage(audioBlob);
                }
                this.cleanupRecording();
            };
            
            this.mediaRecorder.start(100);
            this.updateVoiceUI(true);
            this.startRealTimeTranscription();
            
        } catch (error) {
            console.error('Recording failed:', error);
            this.showError('Microphone access denied or not available');
            this.isHolding = false;
        }
    }

    async endHoldToSpeak() {
        if (!this.isHolding) return;
        
        this.isHolding = false;
        this.isRecording = false;
        
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
        }
        
        this.updateVoiceUI(false);
    }

    cleanupRecording() {
        if (this.voiceStream) {
            this.voiceStream.getTracks().forEach(track => track.stop());
            this.voiceStream = null;
        }
        this.mediaRecorder = null;
        this.isRecording = false;
    }

    updateVoiceUI(isRecording) {
        const voiceBtn = document.getElementById('voice-btn');
        const voiceFeedback = document.getElementById('voice-feedback');
        const transcriptionDisplay = document.getElementById('transcription-display');
        
        if (!voiceBtn || !voiceFeedback || !transcriptionDisplay) return;
        
        if (isRecording) {
            voiceBtn.classList.add('recording');
            voiceBtn.innerHTML = '<i class="fas fa-stop"></i><span class="voice-text">Release to send</span>';
            voiceFeedback.classList.add('active');
            transcriptionDisplay.textContent = 'Listening...';
            this.initializeVoiceVisualizer();
        } else {
            voiceBtn.classList.remove('recording');
            voiceBtn.innerHTML = '<i class="fas fa-microphone"></i><span class="voice-text">Hold to speak</span>';
            voiceFeedback.classList.remove('active');
        }
    }

    startRealTimeTranscription() {
        const transcriptionDisplay = document.getElementById('transcription-display');
        if (!transcriptionDisplay) return;
        
        let dots = 0;
        
        const updateTranscription = () => {
            if (!this.isRecording) return;
            
            dots = (dots + 1) % 4;
            const dotString = '.'.repeat(dots);
            transcriptionDisplay.textContent = `Listening${dotString}`;
            
            setTimeout(updateTranscription, 500);
        };
        
        updateTranscription();
    }

    initializeVoiceVisualizer() {
        const canvas = document.getElementById('voice-canvas');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        const draw = () => {
            if (!this.isRecording) return;
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
            gradient.addColorStop(0, '#7c4dff');
            gradient.addColorStop(1, '#667eea');
            
            ctx.fillStyle = gradient;
            
            const barCount = 20;
            const barWidth = canvas.width / barCount;
            
            for (let i = 0; i < barCount; i++) {
                const height = (Math.random() * 40 + 10) * (this.isRecording ? 1 : 0.3);
                const x = i * barWidth;
                const y = (canvas.height - height) / 2;
                
                ctx.fillRect(x + 2, y, barWidth - 4, height);
            }
            
            requestAnimationFrame(draw);
        };
        
        draw();
    }

    showNotification(message) {
        const existingNotification = document.querySelector('.voice-notification');
        if (existingNotification) {
            existingNotification.remove();
        }

        const notification = document.createElement('div');
        notification.className = 'voice-notification';
        notification.textContent = message;
        
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 24px;
            border-radius: 25px;
            font-size: 14px;
            font-weight: 500;
            z-index: 10000;
            transform: translateX(300px);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        `;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
        }, 100);

        setTimeout(() => {
            notification.style.transform = 'translateX(300px)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }

    loadSavedSettings() {
        try {
            const savedVoiceType = localStorage.getItem('voiceType');
            if (savedVoiceType) {
                this.useCustomVoice = savedVoiceType === 'custom';
                console.log(`Loaded voice type: ${savedVoiceType}, useCustomVoice: ${this.useCustomVoice}`);
            }
        } catch (error) {
            console.error('Error loading saved settings:', error);
            this.useCustomVoice = true; 
        }
    }


    async processVoiceMessage(audioBlob) {
        const recordingDuration = Date.now() - this.recordingStartTime;

        if (recordingDuration < 500) {
            this.showError('Recording too short. Please hold the button longer and speak.');
            return;
        }

        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        formData.append('use_custom_voice', this.useCustomVoice.toString()); 

        this.showTypingIndicator();

        try {
            const response = await fetch('/chat-voice', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                this.displayMessage(data.transcription, 'user');
                await this.handleAIResponse(data);
            } else {
                throw new Error(data.error || 'Voice processing failed');
            }

        } catch (error) {
            console.error('Voice message failed:', error);
            this.showError('Failed to process voice message. Please try again.');
        } finally {
            this.hideTypingIndicator();
        }
    }

    displayMessageWithImage(text, imageUrl, type) {
    const chatMessages = document.getElementById('messages-container'); 
    if (!chatMessages) {
        console.error('messages-container not found in DOM');
        return;
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.innerHTML = type === 'user' 
    ? '<img src="user.jpg" alt="User" style="width:24px;height:24px;">' 
    : '<img src="chatbot.jpg" alt="Bot" style="width:24px;height:24px;">';


    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const imgWrap = document.createElement('div');
    imgWrap.className = 'generated-image-container';

    const safeUrl = String(imageUrl || '').trim();
    imgWrap.innerHTML = `
        <img src="${safeUrl}"
            alt="Generated image"
            class="generated-image"
            loading="lazy"
            referrerpolicy="no-referrer"
            onclick="window.open('${safeUrl}', '_blank')" />
        <div class="image-caption">
        <span class="image-icon">🎨</span>
        <span>Click to view full size</span>
        </div>
    `;
    contentDiv.appendChild(imgWrap);

    const textWrap = document.createElement('div');
    textWrap.className = 'generated-image-text';
    textWrap.innerHTML = renderMarkdownSafely(text);
    contentDiv.appendChild(textWrap);

    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'});

    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(timeDiv);
    chatMessages.appendChild(messageDiv);

    setTimeout(() => {
        chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
    }, 100);
    }
    

    async sendMessage() {
        const input = document.getElementById('message-input');
        if (!input) return;

        const message = input.value.trim();
        if (!message) return;

        const imageInput = document.getElementById('image-input');
        const file = imageInput && imageInput.files && imageInput.files[0];

        input.value = '';
        this.autoResizeTextarea();

        if (file) {
            const localUrl = URL.createObjectURL(file);
            this.displayMessage(message, 'user', { imageSrc: localUrl });
            setTimeout(() => URL.revokeObjectURL(localUrl), 5000);
        } else {
            this.displayMessage(message, 'user');
        }

        this.showTypingIndicator();

        try {
            let response;
            if (file) {
                const fd = new FormData();
                fd.append('message', message);
                fd.append('session_id', this.sessionId || 'default'); 
                fd.append('use_custom_voice', String(this.useCustomVoice ?? true));
                fd.append('context_limit', '10');
                fd.append('image', file);

                response = await fetch('/chat-multimodal', { method: 'POST', body: fd });
            } else {
                response = await fetch('/chat-text', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message,
                        session_id: this.sessionId || 'default',  
                        context_limit: 10,                         
                        use_custom_voice: this.useCustomVoice === true
                    })
                });
            }

            const data = await response.json();
            if (!data || data.success === false) {
                throw new Error((data && data.error) || 'Request failed');
            }

            const normalized = normalizeBackendResponse(data);

            if (normalized.imageUrl) {
            this.displayMessageWithImage(normalized.responseText, normalized.imageUrl, 'ai');

            if (normalized.hasAudio && normalized.audioUrl) {
                try {
                await this.playAudioWithAdvancedLipSync(
                    normalized.audioUrl,
                    normalized.responseText,
                    normalized.emotion
                );
                } catch {
                await this.playAudioWithLipSync(normalized.audioUrl, normalized.emotion);
                }
            }

            this.conversationHistory.push({
                user: normalized.userEcho,
                ai: normalized.responseText,
                emotion: normalized.emotion,
                voiceType: normalized.voiceType,
                mode: normalized.mode,
                timestamp: new Date().toISOString()
            });

            } else {
            await this.handleAIResponse(data);
            }

        } catch (err) {
            console.error(err);
            this.displayMessage("Something went wrong. Please try again.", 'ai');
        } finally {
            this.hideTypingIndicator();
            if (imageInput) imageInput.value = '';
            const previewContainer = document.getElementById('image-preview-container');
            const previewImage = document.getElementById('image-preview');
            if (previewContainer && previewImage) {
                previewImage.src = '';
                previewContainer.style.display = 'none';
            }
        }
    }




    async handleAIResponse(data) {
        const normalized = normalizeBackendResponse(data);

        this.displayMessage(normalized.responseText, 'ai', normalized.emotion);

        if (normalized.voiceType) {
            const voiceTypeDisplay = normalized.voiceType === 'custom' ? 'Custom Voice' : 'Fast Voice';
            console.log(` Using: ${voiceTypeDisplay}`);
            this.showVoiceTypeIndicator(voiceTypeDisplay);
        }

        if (normalized.hasAudio && normalized.audioUrl) {
            try {
                await this.playAudioWithAdvancedLipSync(normalized.audioUrl, normalized.responseText, normalized.emotion);
            } catch {
                await this.playAudioWithLipSync(normalized.audioUrl, normalized.emotion);
            }
        }

        this.conversationHistory.push({
            user: normalized.userEcho,
            ai: normalized.responseText,
            emotion: normalized.emotion,
            voiceType: normalized.voiceType,
            mode: normalized.mode,
            timestamp: new Date().toISOString()
        });

        this.scrollToBottom();
    }

    analyzeTextForPhonemes(text) {
        const words = text.toLowerCase().split(' ');
        const phonemeSequence = [];

        words.forEach(word => {
            const cleanWord = word.replace(/[^\w]/g, '');
            
            for (let i = 0; i < cleanWord.length; i++) {
                const char = cleanWord[i].toUpperCase();
                if (this.phonemeToViseme[char]) {
                    phonemeSequence.push({
                        phoneme: char,
                        viseme: this.phonemeToViseme[char],
                        duration: 0.15
                    });
                }
            }
            
            if (cleanWord.length > 0) {
                phonemeSequence.push({
                    phoneme: 'PAUSE',
                    viseme: 'mouthClosed',
                    duration: 0.1
                });
            }
        });

        return phonemeSequence;
    }
    async playAudioWithAdvancedLipSync(audioUrl, text, emotion = 'neutral') {
        try {
            if (this.currentAudio) {
                this.currentAudio.pause();
            }
            
            const phonemeSequence = this.analyzeTextForPhonemes(text);
            
            const audio = new Audio(audioUrl);
            audio.crossOrigin = "anonymous";
            
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            
            const source = this.audioContext.createMediaElementSource(audio);
            const analyser = this.audioContext.createAnalyser();
            
            analyser.fftSize = 1024;
            const bufferLength = analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);
            
            source.connect(analyser);
            analyser.connect(this.audioContext.destination);
            
            this.currentAudio = audio;
            this.isPlaying = true;
            
            const avatarContainer = document.querySelector('.avatar-container');
            if (avatarContainer) {
                avatarContainer.classList.add('speaking');
            }
            
            this.startEyeAnimation();
            this.startBodyAnimation();
            
            audio.addEventListener('ended', () => {
                this.stopAllAnimations();
                avatarContainer?.classList.remove('speaking');
                this.isPlaying = false;
            });
            
            await audio.play();
            
            this.combinePhonemeWithAudioAnalysis(analyser, dataArray, bufferLength, emotion);
            
        } catch (error) {
            console.error('Advanced lip-sync failed:', error);
            this.isPlaying = false;
        }
    }

    combinePhonemeWithAudioAnalysis(analyser, dataArray, bufferLength, emotion) {
        const animate = () => {
            if (!this.isPlaying || this.currentAudio?.paused || this.currentAudio?.ended) {
                this.setMouthOpen(0, emotion);
                return;
            }
            
            analyser.getByteTimeDomainData(dataArray);
            
            let sum = 0;
            for (let i = 0; i < bufferLength; i++) {
                const amplitude = (dataArray[i] - 128) / 128;
                sum += amplitude * amplitude;
            }
            const volume = Math.sqrt(sum / bufferLength);
            
            const mouthAmount = Math.min(volume * 5, 1); 
            this.setMouthOpen(mouthAmount, emotion);
            
            requestAnimationFrame(animate);
        };
        
        animate();
    }

    startEyeAnimation() {
        this.eyeAnimationActive = true;
        
        const animateEyes = () => {
            if (!this.eyeAnimationActive || !this.avatar) return;
            
            this.avatar.traverse((child) => {
                if (child.isMesh && child.morphTargetDictionary) {
                    if (Math.random() < 0.02) { 
                        this.animateBlink(child);
                    }
                    
                    if (Math.random() < 0.01) { 
                        this.animateEyeMovement(child);
                    }
                }
            });
            
            setTimeout(animateEyes, 50);
        };
        
        animateEyes();
    }

    animateBlink(mesh) {
        const blinkTargets = ['eyeBlinkLeft', 'eyeBlinkRight', 'blink'];
        
        blinkTargets.forEach(target => {
            if (mesh.morphTargetDictionary[target] !== undefined) {
                const blinkIndex = mesh.morphTargetDictionary[target];
                
                const closeAnimation = () => {
                    mesh.morphTargetInfluences[blinkIndex] = Math.min(1, mesh.morphTargetInfluences[blinkIndex] + 0.3);
                    if (mesh.morphTargetInfluences[blinkIndex] < 1) {
                        requestAnimationFrame(closeAnimation);
                    } else {
                        setTimeout(() => {
                            const openAnimation = () => {
                                mesh.morphTargetInfluences[blinkIndex] = Math.max(0, mesh.morphTargetInfluences[blinkIndex] - 0.3);
                                if (mesh.morphTargetInfluences[blinkIndex] > 0) {
                                    requestAnimationFrame(openAnimation);
                                }
                            };
                            openAnimation();
                        }, 100);
                    }
                };
                closeAnimation();
            }
        });
    }

    animateEyeMovement(mesh) {
        const eyeTargets = ['eyeLookLeft', 'eyeLookRight', 'eyeLookUp', 'eyeLookDown'];
        
        eyeTargets.forEach(target => {
            if (mesh.morphTargetDictionary[target] !== undefined) {
                const targetIndex = mesh.morphTargetDictionary[target];
                const targetValue = (Math.random() - 0.5) * 0.3; // حرکت ملایم
                
                const animateToTarget = () => {
                    const current = mesh.morphTargetInfluences[targetIndex] || 0;
                    const diff = targetValue - current;
                    
                    if (Math.abs(diff) > 0.01) {
                        mesh.morphTargetInfluences[targetIndex] = current + (diff * 0.1);
                        requestAnimationFrame(animateToTarget);
                    } else {
                        setTimeout(() => {
                            const returnToNormal = () => {
                                const current = mesh.morphTargetInfluences[targetIndex] || 0;
                                if (Math.abs(current) > 0.01) {
                                    mesh.morphTargetInfluences[targetIndex] = current * 0.9;
                                    requestAnimationFrame(returnToNormal);
                                }
                            };
                            returnToNormal();
                        }, 1000);
                    }
                };
                
                animateToTarget();
            }
        });
    }

    startBodyAnimation() {
        this.bodyAnimationActive = true;
        
        const animateBody = () => {
            if (!this.bodyAnimationActive || !this.avatar) return;
            
            this.avatar.traverse((child) => {
                if (child.isBone || child.type === 'Bone') {
                    const boneName = child.name.toLowerCase();
                    
                    if (boneName.includes('hand') || boneName.includes('arm')) {
                        this.animateHandGestures(child);
                    }
                    
                    if (boneName.includes('head') || boneName.includes('neck')) {
                        this.animateHeadMovements(child);
                    }
                    
                    if (boneName.includes('chest') || boneName.includes('spine')) {
                        this.animateBreathing(child);
                    }
                }
            });
            
            setTimeout(animateBody, 100);
        };
        
        animateBody();
    }


    animateHandGestures(bone) {
        if (Math.random() < 0.005) {
            const originalRotation = {
                x: bone.rotation.x,
                y: bone.rotation.y,
                z: bone.rotation.z
            };

            const gestureIntensity = 0.1;
            bone.rotation.x += (Math.random() - 0.5) * gestureIntensity;
            bone.rotation.y += (Math.random() - 0.5) * gestureIntensity;
            bone.rotation.z += (Math.random() - 0.5) * gestureIntensity;

            setTimeout(() => {
                const returnToOriginal = () => {
                    const diffX = originalRotation.x - bone.rotation.x;
                    const diffY = originalRotation.y - bone.rotation.y;
                    const diffZ = originalRotation.z - bone.rotation.z;
                    const distance = Math.sqrt(diffX*diffX + diffY*diffY + diffZ*diffZ);

                    if (distance > 0.01) {
                        bone.rotation.x += diffX * 0.05;
                        bone.rotation.y += diffY * 0.05;
                        bone.rotation.z += diffZ * 0.05;
                        requestAnimationFrame(returnToOriginal);
                    } else {
                        bone.rotation.x = originalRotation.x;
                        bone.rotation.y = originalRotation.y;
                        bone.rotation.z = originalRotation.z;
                    }
                };
                returnToOriginal();
            }, 2000);
        }
    }



    animateHeadMovements(bone) {
        if (Math.random() < 0.01) {
            const originalRotation = {
                x: bone.rotation.x,
                y: bone.rotation.y,
                z: bone.rotation.z
            };

            bone.rotation.y += (Math.random() - 0.5) * 0.2;
            bone.rotation.x += (Math.random() - 0.5) * 0.1;

            setTimeout(() => {
                const returnToOriginal = () => {
                    const diffX = originalRotation.x - bone.rotation.x;
                    const diffY = originalRotation.y - bone.rotation.y;
                    const diffZ = originalRotation.z - bone.rotation.z;
                    const distance = Math.sqrt(diffX*diffX + diffY*diffY + diffZ*diffZ);

                    if (distance > 0.01) {
                        bone.rotation.x += diffX * 0.03;
                        bone.rotation.y += diffY * 0.03;
                        bone.rotation.z += diffZ * 0.03;
                        requestAnimationFrame(returnToOriginal);
                    } else {
                        bone.rotation.x = originalRotation.x;
                        bone.rotation.y = originalRotation.y;
                        bone.rotation.z = originalRotation.z;
                    }
                };
                returnToOriginal();
            }, 1500);
        }
    }


    animateBreathing(bone) {
        const time = Date.now() * 0.001;
        const breathingIntensity = 0.02;
        
        const targetScale = 1 + Math.sin(time * 0.5) * breathingIntensity;
        bone.scale.y = targetScale;
    }


    stopAllAnimations() {
        this.eyeAnimationActive = false;
        this.bodyAnimationActive = false;
        this.setMouthOpen(0, 'neutral');
    }

    async playAudioWithLipSync(audioUrl, emotion = 'neutral') {
        try {
            if (this.currentAudio) {
                this.currentAudio.pause();
            }
            
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            
            const audio = new Audio(audioUrl);
            audio.crossOrigin = "anonymous";
            
            const source = this.audioContext.createMediaElementSource(audio);
            const analyser = this.audioContext.createAnalyser();
            
            analyser.fftSize = 256;
            const bufferLength = analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);
            
            source.connect(analyser);
            analyser.connect(this.audioContext.destination);
            
            const animateLipSync = () => {
                if (audio.paused || audio.ended) {
                    this.setMouthOpen(0, emotion);
                    const avatarContainer = document.querySelector('.avatar-container');
                    if (avatarContainer) {
                        avatarContainer.classList.remove('speaking');
                    }
                    return;
                }
                
                analyser.getByteTimeDomainData(dataArray);
                
                let sum = 0;
                for (let i = 0; i < bufferLength; i++) {
                    const amplitude = (dataArray[i] - 128) / 128;
                    sum += amplitude * amplitude;
                }
                const volume = Math.sqrt(sum / bufferLength);
                
                this.setMouthOpen(volume * 4, emotion); 
                
                requestAnimationFrame(animateLipSync);
            };
            
            this.currentAudio = audio;
            
            const avatarContainer = document.querySelector('.avatar-container');
            if (avatarContainer) {
                avatarContainer.classList.add('speaking');
            }
            
            audio.addEventListener('ended', () => {
                avatarContainer?.classList.remove('speaking');
                this.setMouthOpen(0, emotion);
                this.isPlaying = false;
            });
            
            this.isPlaying = true;
            await audio.play();
            animateLipSync();
            
        } catch (error) {
            console.error('Lip-sync playback failed:', error);
            this.isPlaying = false;
        }
    }

    setMouthOpen(amount, emotion = 'neutral') {
        if (!this.avatar) return;
        
        amount = Math.max(0, Math.min(amount, 1));
        
        this.avatar.traverse((child) => {
            if (child.isMesh && child.morphTargetInfluences && child.morphTargetDictionary) {
                const mouthTargets = ['mouthOpen', 'jawOpen', 'JawOpen', 'jaw_open', 'mouth_open'];
                for (const target of mouthTargets) {
                    if (child.morphTargetDictionary[target] !== undefined) {
                        child.morphTargetInfluences[child.morphTargetDictionary[target]] = amount;
                        break;
                    }
                }
                
                const smileTargets = ['mouthSmile', 'smile', 'Smile'];
                for (const target of smileTargets) {
                    if (child.morphTargetDictionary[target] !== undefined) {
                        let smileAmount = 0;
                        switch(emotion) {
                            case 'happy':
                                smileAmount = 0.4;
                                break;
                            case 'neutral':
                                smileAmount = 0.1;
                                break;
                            case 'sad':
                                smileAmount = 0;
                                break;
                            default:
                                smileAmount = 0.1;
                        }
                        child.morphTargetInfluences[child.morphTargetDictionary[target]] = smileAmount;
                        break;
                    }
                }
            }
        });
    }

    displayMessage(content, sender, options = {}) {
        const container = document.getElementById('messages-container');
        if (!container) return;

        const { imageSrc } = options;

        if (sender === 'ai') {
            const welcomeMessage = container.querySelector('.welcome-message');
            if (welcomeMessage) {
                welcomeMessage.remove();
            }
        }

        const message = document.createElement('div');
        message.className = `message ${sender}`;

        const avatar = document.createElement('div');
        avatar.className = 'avatar-placeholder';
        avatar.innerHTML = sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-user-astronaut"></i>';

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        bubble.style.display = 'flex';
        bubble.style.flexDirection = 'column';
        bubble.style.alignItems = 'flex-start'; 

        if (imageSrc && sender === 'user') {
            const img = document.createElement('img');
            img.src = imageSrc;
            img.alt = 'uploaded';
            img.className = 'msg-image';
            img.style.maxWidth = '220px';
            img.style.maxHeight = '220px';
            img.style.borderRadius = '12px';
            img.style.objectFit = 'cover';
            img.style.display = 'block';
            img.style.marginBottom = '8px';
            bubble.appendChild(img);
        }

        const p = document.createElement('p');
        p.textContent = content;
        p.style.margin = '0';         
        p.style.lineHeight = '1.5';
        bubble.appendChild(p);

        message.appendChild(avatar);
        message.appendChild(bubble);

        container.appendChild(message);
        this.scrollToBottom();
    }



    async playResponse(audioUrl) {
        if (!audioUrl) {
            console.warn('No audio URL provided');
            return;
        }

        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio = null;
        }

        try {
            this.currentAudio = new Audio(audioUrl);
            this.isPlaying = true;

            const avatarContainer = document.querySelector('.avatar-container');
            if (avatarContainer) {
                avatarContainer.classList.add('speaking');
            }

            this.currentAudio.addEventListener('play', () => {
                this.isPlaying = true;
            });

            this.currentAudio.addEventListener('ended', () => {
                this.isPlaying = false;
                if (avatarContainer) {
                    avatarContainer.classList.remove('speaking');
                }
            });

            this.currentAudio.addEventListener('error', (e) => {
                this.isPlaying = false;
                if (avatarContainer) {
                    avatarContainer.classList.remove('speaking');
                }
            });

            await this.currentAudio.play();
            
        } catch (error) {
            this.isPlaying = false;
            const avatarContainer = document.querySelector('.avatar-container');
            if (avatarContainer) {
                avatarContainer.classList.remove('speaking');
            }
        }
    }

    updateEmotion(emotion) {
        this.currentEmotion = emotion;
        const display = document.getElementById('emotion-display');
        if (!display) return;
        
        const label = display.querySelector('.emotion-label');
        if (!label) return;
        
        label.textContent = emotion.charAt(0).toUpperCase() + emotion.slice(1);
        
        const emotionColors = {
            happy: '#4caf50',
            sad: '#2196f3',
            angry: '#f44336',
            surprised: '#ff9800',
            neutral: '#7c4dff',
            anxious: '#ff5722',
            confident: '#00bcd4'
        };
        
        const color = emotionColors[emotion] || emotionColors.neutral;
        display.style.backgroundColor = color + '20';
        display.style.borderColor = color;
        display.style.color = color;
    }

    showTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.classList.add('active');
        }
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.classList.remove('active');
        }
    }

    stopPlayback() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.isPlaying = false;
            
            const avatarContainer = document.querySelector('.avatar-container');
            if (avatarContainer) {
                avatarContainer.classList.remove('speaking');
            }
        }
        
        this.stopAllAnimations();
    }

    regenerateResponse() {
        if (this.conversationHistory.length > 0) {
            const lastEntry = this.conversationHistory[this.conversationHistory.length - 1];
            const input = document.getElementById('message-input');
            if (input) {
                input.value = lastEntry.user;
                this.sendMessage();
            }
        }
    }

    exportSession() {
        const data = {
            session: this.conversationHistory,
            timestamp: new Date().toISOString(),
            totalMessages: this.conversationHistory.length,
            psychologist: 'Dr. Alfred Adler'
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `adler-session-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
    }

    toggleTheme() {
        const body = document.body;
        const icon = document.querySelector('#theme-toggle i');
        
        if (body.dataset.theme === 'dark') {
            body.dataset.theme = 'light';
            if (icon) icon.className = 'fas fa-moon';
        } else {
            body.dataset.theme = 'dark';
            if (icon) icon.className = 'fas fa-sun';
        }
        
        localStorage.setItem('theme', body.dataset.theme);
    }

    autoResizeTextarea() {
        const textarea = document.getElementById('message-input');
        if (!textarea) return;
        
        const resize = () => {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
        };
        
        textarea.addEventListener('input', resize);
        resize();
    }

    scrollToBottom() {
        const container = document.getElementById('messages-container');
        if (container) {
            container.scrollTo({
                top: container.scrollHeight,
                behavior: 'smooth'
            });
        }
    }

    showError(message) {
        const container = document.getElementById('messages-container');
        if (!container) return;
        
        const error = document.createElement('div');
        error.className = 'message ai';
        error.innerHTML = `
            <div class="avatar-placeholder" style="background: linear-gradient(135deg, #f44336, #e91e63);">
                <i class="fas fa-exclamation-triangle"></i>
            </div>
            <div class="message-bubble" style="background: var(--surface); border-left: 4px solid #f44336;">
                ${message}
            </div>
        `;
        
        container.appendChild(error);
        this.scrollToBottom();
        
        setTimeout(() => {
            if (error.parentNode) {
                error.remove();
            }
        }, 5000);
    }

    handleResize() {
        const canvas = document.getElementById('avatar-canvas');
        if (!canvas || !this.camera || !this.renderer) return;
        
        this.camera.aspect = canvas.offsetWidth / canvas.offsetHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
    }

    increaseBrightness() {
        if (this.avatar) {
            this.avatar.traverse((child) => {
                if (child.isMesh && child.material && child.material.color) {
                    child.material.color.multiplyScalar(1.2);
                    child.material.needsUpdate = true;
                }
            });
        }
    }

    decreaseBrightness() {
        if (this.avatar) {
            this.avatar.traverse((child) => {
                if (child.isMesh && child.material && child.material.color) {
                    child.material.color.multiplyScalar(0.8);
                    child.material.needsUpdate = true;
                }
            });
        }
    }

    adjustExposure(value) {
        if (this.renderer) {
            this.renderer.toneMappingExposure = value;
        }
    }

    setCameraDistance(distance) {
        if (this.camera) {
            this.camera.position.setZ(distance);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.body.dataset.theme = savedTheme;
    const icon = document.querySelector('#theme-toggle i');
    if (icon) {
        icon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
    
    window.voiceAssistant = new VoiceAssistant();
});
document.getElementById("image-input").addEventListener("change", function (event) {
    const file = event.target.files[0];
    const previewContainer = document.getElementById("image-preview-container");
    const previewImage = document.getElementById("image-preview");

    if (file) {
        const reader = new FileReader();
        reader.onload = function (e) {
            previewImage.src = e.target.result;
            previewContainer.style.display = "block";
        };
        reader.readAsDataURL(file);
    } else {
        previewImage.src = "";
        previewContainer.style.display = "none";
    }
});
const imageInput = document.getElementById("image-input");
const previewContainer = document.getElementById("image-preview-container");
const previewImage = document.getElementById("image-preview");
const removePreview = document.getElementById("remove-preview");

imageInput.addEventListener("change", function (event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function (e) {
            previewImage.src = e.target.result;
            previewContainer.style.display = "inline-block";
        };
        reader.readAsDataURL(file);
    } else {
        previewImage.src = "";
        previewContainer.style.display = "none";
    }
});

removePreview.addEventListener("click", function () {
    previewImage.src = "";
    previewContainer.style.display = "none";
    imageInput.value = ""; 
});
function normalizeBackendResponse(data) {
  const mode = data.mode || 'conversation';

  const responseText =
    data.response ??
    data.pretty_text ??
    data.message ??    
    '';

  const userEcho = data.message || data.transcription || '';

  const hasAudio = !!data.has_audio && !!data.audio_url;
  const audioUrl = hasAudio ? data.audio_url : null;

  const imageUrl = data.image_url || null;

  const emotion = data.emotion || 'neutral';
  const voiceType = data.voice_type || (data.has_audio ? (data.use_custom_voice ? 'custom' : 'fast') : undefined);

  return {
    mode,
    responseText,
    userEcho,
    hasAudio,
    audioUrl,
    imageUrl,
    emotion,
    voiceType
  };
}
function renderMarkdownSafely(text) {
  if (window.marked && typeof window.marked.parse === 'function') {
    try { return window.marked.parse(text); } catch (e) {}
  }
  const div = document.createElement('div');
  div.textContent = text ?? '';
  return div.innerHTML.replace(/\n/g, '<br>');
}