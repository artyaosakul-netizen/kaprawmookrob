/**
 * FoodShield AI - User Interface, Navigation & Theme Module
 */

const UI = {
  // DOM Elements cache
  elements: {},

  // Active theme mode: 'system' | 'dark' | 'light'
  currentThemeMode: 'system',

  init() {
    this.cacheElements();
    this.initTheme();
    this.bindEvents();
    this.updateSliderDisplays();
  },

  cacheElements() {
    this.elements = {
      form: document.getElementById('riskForm'),
      cropType: document.getElementById('cropType'),
      cropDamage: document.getElementById('cropDamage'),
      cropDamageVal: document.getElementById('cropDamageVal'),
      weather: document.getElementById('weather'),
      water: document.getElementById('water'),
      symptomsGrid: document.getElementById('symptomsGrid'),
      nearbyOutbreakYes: document.getElementById('outbreakYes'),
      nearbyOutbreakNo: document.getElementById('outbreakNo'),
      livestockDep: document.getElementById('livestockDep'),
      livestockDepVal: document.getElementById('livestockDepVal'),
      priceTrend: document.getElementById('priceTrend'),
      additionalNotes: document.getElementById('additionalNotes'),

      // Buttons & Theme Toggle
      btnAnalyze: document.getElementById('btnAnalyze'),
      btnDemo: document.getElementById('btnDemo'),
      themeToggleBtn: document.getElementById('themeToggleBtn'),

      // Navigation & Page Views
      navTabs: document.querySelectorAll('.nav-tab-btn'),
      toolView: document.getElementById('toolView'),
      aboutView: document.getElementById('aboutView'),
      guidanceView: document.getElementById('guidanceView'),
      researchView: document.getElementById('researchView'),

      // Sections
      resultsContainer: document.getElementById('resultsContainer'),
      placeholderSection: document.getElementById('placeholderSection'),
      loadingSection: document.getElementById('loadingSection'),
      loadingText: document.getElementById('loadingText'),
      errorBanner: document.getElementById('errorBanner'),
      errorMessage: document.getElementById('errorMessage'),
      outputSection: document.getElementById('outputSection'),

      // Output Elements
      riskScoreNum: document.getElementById('riskScoreNum'),
      riskBadge: document.getElementById('riskBadge'),
      riskMeterFill: document.getElementById('riskMeterFill'),
      aiSummaryText: document.getElementById('aiSummaryText'),
      causesList: document.getElementById('causesList'),
      immediateActionsList: document.getElementById('immediateActionsList'),
      shortTermActionsList: document.getElementById('shortTermActionsList'),
      longTermActionsList: document.getElementById('longTermActionsList'),
      dominoTimeline: document.getElementById('dominoTimeline')
    };
  },

  /* ================= Theme Management ================= */

  initTheme() {
    // Read saved preference or default to 'system'
    const savedTheme = localStorage.getItem('foodshield_theme') || 'system';
    this.setThemeMode(savedTheme);

    // Watch for device system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', () => {
      if (this.currentThemeMode === 'system') {
        this.applyTheme('system');
      }
    });
  },

  setThemeMode(mode) {
    this.currentThemeMode = mode;
    localStorage.setItem('foodshield_theme', mode);
    this.applyTheme(mode);
  },

  applyTheme(mode) {
    let resolvedTheme = mode;

    if (mode === 'system') {
      const isSystemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      resolvedTheme = isSystemDark ? 'dark' : 'light';
    }

    document.documentElement.setAttribute('data-theme', resolvedTheme);
    this.updateThemeButtonUI(mode);
  },

  updateThemeButtonUI(mode) {
    if (!this.elements.themeToggleBtn) return;

    if (mode === 'system') {
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      this.elements.themeToggleBtn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        อุปกรณ์ (${isDark ? 'มืด' : 'สว่าง'})
      `;
    } else if (mode === 'dark') {
      this.elements.themeToggleBtn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        โหมดมืด
      `;
    } else {
      this.elements.themeToggleBtn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
        โหมดสว่าง
      `;
    }
  },

  cycleThemeMode() {
    const modes = ['system', 'dark', 'light'];
    const nextIdx = (modes.indexOf(this.currentThemeMode) + 1) % modes.length;
    this.setThemeMode(modes[nextIdx]);
  },

  /* ================= Event Bindings ================= */

  bindEvents() {
    // Theme toggle button click
    if (this.elements.themeToggleBtn) {
      this.elements.themeToggleBtn.addEventListener('click', () => {
        this.cycleThemeMode();
      });
    }

    // Tab switching event listeners
    if (this.elements.navTabs) {
      this.elements.navTabs.forEach(tabBtn => {
        tabBtn.addEventListener('click', (e) => {
          const btn = e.currentTarget || e.target.closest('.nav-tab-btn');
          const targetTab = btn ? (btn.getAttribute('data-tab') || btn.dataset.tab) : null;
          if (targetTab) {
            this.switchTab(targetTab);
          }
        });
      });
    }

    // Slider listeners
    if (this.elements.cropDamage) {
      this.elements.cropDamage.addEventListener('input', () => {
        this.elements.cropDamageVal.textContent = `${this.elements.cropDamage.value}%`;
      });
    }

    if (this.elements.livestockDep) {
      this.elements.livestockDep.addEventListener('input', () => {
        this.elements.livestockDepVal.textContent = `${this.elements.livestockDep.value}%`;
      });
    }

    // Demo button
    if (this.elements.btnDemo) {
      this.elements.btnDemo.addEventListener('click', () => this.loadDemoScenario());
    }
  },

  /**
   * SPA View Switcher
   * @param {string} tabId 
   */
  switchTab(tabId) {
    if (!tabId) return;

    // Refresh view element references
    const toolView = document.getElementById('toolView');
    const aboutView = document.getElementById('aboutView');
    const guidanceView = document.getElementById('guidanceView');
    const researchView = document.getElementById('researchView');

    const navTabs = document.querySelectorAll('.nav-tab-btn');
    navTabs.forEach(btn => {
      const bTab = btn.getAttribute('data-tab') || btn.dataset.tab;
      if (bTab === tabId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    const allViews = [toolView, aboutView, guidanceView, researchView];
    allViews.forEach(view => {
      if (view) view.classList.add('hidden');
    });

    if (tabId === 'tool' && toolView) toolView.classList.remove('hidden');
    if (tabId === 'about' && aboutView) aboutView.classList.remove('hidden');
    if (tabId === 'guidance' && guidanceView) guidanceView.classList.remove('hidden');
    if (tabId === 'research' && researchView) researchView.classList.remove('hidden');

    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  updateSliderDisplays() {
    if (this.elements.cropDamageVal && this.elements.cropDamage) {
      this.elements.cropDamageVal.textContent = `${this.elements.cropDamage.value}%`;
    }
    if (this.elements.livestockDepVal && this.elements.livestockDep) {
      this.elements.livestockDepVal.textContent = `${this.elements.livestockDep.value}%`;
    }
  },

  getFormData() {
    const selectedSymptoms = [];
    const symptomCheckboxes = document.querySelectorAll('input[name="symptoms"]:checked');
    symptomCheckboxes.forEach(cb => selectedSymptoms.push(cb.value));

    const nearbyOutbreak = document.querySelector('input[name="outbreak"]:checked')?.value || 'ไม่มี';

    return {
      cropType: this.elements.cropType.value,
      cropDamage: parseInt(this.elements.cropDamage.value, 10),
      weather: this.elements.weather.value,
      water: this.elements.water.value,
      symptoms: selectedSymptoms,
      nearbyOutbreak: nearbyOutbreak,
      livestockDep: parseInt(this.elements.livestockDep.value, 10),
      priceTrend: this.elements.priceTrend.value,
      additionalNotes: this.elements.additionalNotes ? this.elements.additionalNotes.value.trim() : ''
    };
  },

  loadDemoScenario() {
    this.switchTab('tool');

    this.elements.cropType.value = 'ข้าว (Rice)';
    this.elements.cropDamage.value = 45;
    this.elements.weather.value = 'ฝนตกหนัก (Heavy Rain)';
    this.elements.water.value = 'น้อย (Low)';
    this.elements.nearbyOutbreakYes.checked = true;
    this.elements.livestockDep.value = 75;
    this.elements.priceTrend.value = 'พุ่งสูงขึ้นอย่างรวดเร็ว (Rapidly Increasing)';

    const symptomsToSelect = ['ใบเปลี่ยนสี/ใบเหลือง', 'เน่า'];
    const symptomCheckboxes = document.querySelectorAll('input[name="symptoms"]');
    symptomCheckboxes.forEach(cb => {
      cb.checked = symptomsToSelect.includes(cb.value);
    });

    if (this.elements.additionalNotes) {
      this.elements.additionalNotes.value = 'พบการระบาดของโรคขอบใบแห้งและเชื้อราลุกลามตามทิศทางลมใน 3 ตำบลใกล้เคียง คลองชลประทานตื้นเขินจากน้ำท่วมขัง และปศุสัตว์ในพื้นที่กำลังขาดแคลนรำข้าวผสมอาหารสัตว์';
    }

    this.updateSliderDisplays();

    const formCard = document.querySelector('.glass-card');
    if (formCard) {
      formCard.style.borderColor = 'var(--accent-green-bright)';
      setTimeout(() => {
        formCard.style.borderColor = '';
      }, 600);
    }
  },

  loadingInterval: null,

  showLoading() {
    this.elements.placeholderSection.classList.add('hidden');
    this.elements.errorBanner.classList.add('hidden');
    this.elements.outputSection.classList.add('hidden');
    this.elements.loadingSection.classList.remove('hidden');

    this.elements.btnAnalyze.disabled = true;
    this.elements.btnAnalyze.innerHTML = `
      <span class="pulse-dot"></span> กำลังวิเคราะห์ข้อมูลด้วย AI...
    `;

    const messages = [
      "1. กำลังอ่านข้อมูลและข้อสังเกตจากพื้นที่ของคุณ...",
      "2. กำลังประเมินผลกระทบต่อพืชผลและอาหารสัตว์...",
      "3. กำลังคาดการณ์ผลกระทบต่อเนื่องที่จะเกิดขึ้น...",
      "4. กำลังสรุปแนวทางแก้ไขและข้อแนะนำที่ทำได้จริง..."
    ];
    let msgIdx = 0;
    this.elements.loadingText.textContent = messages[0];

    clearInterval(this.loadingInterval);
    this.loadingInterval = setInterval(() => {
      msgIdx = (msgIdx + 1) % messages.length;
      this.elements.loadingText.textContent = messages[msgIdx];
    }, 1600);

    this.scrollToResults();
  },

  hideLoading() {
    clearInterval(this.loadingInterval);
    this.elements.loadingSection.classList.add('hidden');
    this.elements.btnAnalyze.disabled = false;
    this.elements.btnAnalyze.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      🚀 วิเคราะห์ความเสี่ยงด้วย AI
    `;
  },

  showError(message) {
    this.hideLoading();
    this.elements.outputSection.classList.add('hidden');
    this.elements.errorBanner.classList.remove('hidden');
    this.elements.errorMessage.textContent = message || "ระบบไม่สามารถวิเคราะห์ข้อมูลได้ในขณะนี้ โปรดตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่อีกครั้ง";
    this.scrollToResults();
  },

  renderResults(data) {
    this.hideLoading();
    this.elements.placeholderSection.classList.add('hidden');
    this.elements.errorBanner.classList.add('hidden');
    this.elements.outputSection.classList.remove('hidden');

    const score = Math.max(0, Math.min(100, parseInt(data.risk_score || 0, 10)));
    
    let category = "ความเสี่ยงต่ำ";
    let badgeClass = "badge-low";
    let meterClass = "fill-low";

    if (score >= 75) {
      category = "ความเสี่ยงวิกฤต (CRITICAL)";
      badgeClass = "badge-critical";
      meterClass = "fill-critical";
    } else if (score >= 50) {
      category = "ความเสี่ยงสูง (HIGH)";
      badgeClass = "badge-high";
      meterClass = "fill-high";
    } else if (score >= 25) {
      category = "ความเสี่ยงปานกลาง (MODERATE)";
      badgeClass = "badge-moderate";
      meterClass = "fill-moderate";
    } else {
      category = "ความเสี่ยงต่ำ (LOW)";
      badgeClass = "badge-low";
      meterClass = "fill-low";
    }

    this.animateScoreNumber(score);

    this.elements.riskBadge.className = `risk-badge ${badgeClass}`;
    this.elements.riskBadge.textContent = category;

    this.elements.riskMeterFill.className = `risk-meter-fill ${meterClass}`;
    setTimeout(() => {
      this.elements.riskMeterFill.style.width = `${score}%`;
    }, 100);

    this.elements.aiSummaryText.textContent = data.summary || "ไม่มีข้อมูลสรุปสถานการณ์";

    this.elements.causesList.innerHTML = '';
    const causes = data.causes || [];
    if (causes.length === 0) {
      this.elements.causesList.innerHTML = '<span class="factor-tag">ความตึงเครียดทั่วไปด้านการเกษตร</span>';
    } else {
      causes.forEach(cause => {
        const tag = document.createElement('span');
        tag.className = 'factor-tag';
        tag.textContent = cause;
        this.elements.causesList.appendChild(tag);
      });
    }

    this.renderActionList(this.elements.immediateActionsList, data.immediate_actions);
    this.renderActionList(this.elements.shortTermActionsList, data.short_term_actions);
    this.renderActionList(this.elements.longTermActionsList, data.long_term_actions);

    this.renderDominoTimeline(data.domino_effect || []);

    this.scrollToResults();
  },

  animateScoreNumber(targetScore) {
    let current = 0;
    const duration = 800;
    const stepTime = 20;
    const steps = duration / stepTime;
    const increment = targetScore / steps;

    const timer = setInterval(() => {
      current += increment;
      if (current >= targetScore) {
        current = targetScore;
        clearInterval(timer);
      }
      this.elements.riskScoreNum.textContent = Math.round(current);
    }, stepTime);
  },

  renderActionList(containerEl, items) {
    containerEl.innerHTML = '';
    if (!items || items.length === 0) {
      containerEl.innerHTML = '<li class="action-item">ไม่มีข้อแนะนำเฉพาะเจาะจง</li>';
      return;
    }
    items.forEach(itemText => {
      const li = document.createElement('li');
      li.className = 'action-item';
      li.textContent = itemText;
      containerEl.appendChild(li);
    });
  },

  renderDominoTimeline(steps) {
    this.elements.dominoTimeline.innerHTML = '';
    if (!steps || steps.length === 0) {
      steps = [
        "ตรวจพบความเสียหายของพืชผล",
        "ผลผลิตทางการเกษตรในภูมิภาคลดลง",
        "เกิดความตึงเครียดในห่วงโซ่อาหารสัตว์",
        "ราคาอาหารพุ่งสูงขึ้น"
      ];
    }

    steps.forEach((stepText, idx) => {
      const stepEl = document.createElement('div');
      stepEl.className = 'timeline-step';
      stepEl.style.animationDelay = `${idx * 0.12}s`;

      stepEl.innerHTML = `
        <div class="step-node">${idx + 1}</div>
        <div class="step-content">
          <div class="step-text">${stepText}</div>
        </div>
      `;
      this.elements.dominoTimeline.appendChild(stepEl);
    });
  },

  scrollToResults() {
    this.elements.resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};
