const RaidJoin = {
  _polling: null,
  _onMapTab: false,
  _joined: false,
  _latest: null,
  _lastStatus: null,
  _lastRaidId: null,
  _resultsShownFor: null,   // raid_id we've already popped the results modal for

  startPolling: function() {
    var self = this;
    if (self._polling) clearInterval(self._polling);
    self._poll();
    self._polling = setInterval(function() {
      if (self._onMapTab) self._poll();
    }, 30000);
  },

  onTabChange: function(tabName) {
    this._onMapTab = (tabName === 'map');
    if (this._onMapTab) this._poll();
  },

  _poll: async function() {
    try {
      var res  = await fetch('/raid/status');
      var data = await res.json();
      this._latest = data;
      var icon = document.getElementById('raid-icon-btn');
      if (icon) icon.classList.toggle('show', data.status === 'join_window');
      if (data.status === 'join_window') this._renderModal(data);

      var bar = document.getElementById('raid-boss-bar');
      if (data.status === 'active') {
        if (bar) {
          bar.classList.add('show');
          var nameEl = document.getElementById('raid-boss-name');
          if (nameEl) nameEl.textContent = '⚔️ ' + (data.boss_name || 'Raid Boss');
        }
        if (window.BuildAttackButton) window.BuildAttackButton.setAttackMode(true);
        this.updateBossBar(data.boss_current_hp, data.boss_max_hp);
        this._lastRaidId = data.raid_id;
      } else {
        if (bar) bar.classList.remove('show');
        if (window.BuildAttackButton) window.BuildAttackButton.setAttackMode(false);
        // Bystanders (didn't land the killing blow) find out the raid ended
        // here, up to 30s later — whoever attacked last already saw the
        // results modal instantly via /raid/attack's own response.
        if (this._lastStatus === 'active' && this._lastRaidId) {
          this._fetchAndShowResults(this._lastRaidId);
        }
      }
      this._lastStatus = data.status;
    } catch (e) {}
  },

  _fetchAndShowResults: async function(raidId) {
    try {
      var res  = await fetch('/raid/results/' + raidId);
      var data = await res.json();
      if (data.status === 'success') this.showResults(data);
    } catch (e) {}
  },

  // Called on every poll and after a self-attack settles, so the bar reflects
  // damage from any participant, not just the local player's own rolls.
  updateBossBar: function(currentHp, maxHp) {
    if (currentHp == null || maxHp == null) return;
    var fill = document.getElementById('raid-boss-hp-fill');
    var text = document.getElementById('raid-boss-hp-text');
    var pct  = maxHp > 0 ? Math.max(0, Math.min(100, Math.round((currentHp / maxHp) * 100))) : 0;
    if (fill) fill.style.width = pct + '%';
    if (text) text.textContent = currentHp.toLocaleString() + ' / ' + maxHp.toLocaleString() + ' HP';
    if (window.BuildAttackButton) window.BuildAttackButton.onBossHpUpdate(currentHp);
  },

  openModal: function() {
    if (!this._latest) return;
    this._renderModal(this._latest);
    document.getElementById('raid-modal-overlay').classList.add('show');
    if (window.GameSounds) GameSounds.modalOpen();
  },

  closeModal: function() {
    document.getElementById('raid-modal-overlay').classList.remove('show');
    if (window.GameSounds) GameSounds.modalClose();
  },

  _renderModal: function(data) {
    var boss = document.getElementById('raid-modal-boss');
    var count = document.getElementById('raid-modal-participants');
    var reward = document.getElementById('raid-modal-reward');
    var btn = document.getElementById('raid-join-btn');
    if (boss)   boss.textContent = data.boss_name || '';
    if (count)  count.textContent = data.participant_count != null ? data.participant_count : 0;
    if (reward) reward.textContent = data.reward_preview || '';
    if (btn && this._joined) {
      btn.disabled = true;
      btn.textContent = 'Joined ✓';
    }
  },

  join: async function() {
    try {
      var res  = await fetch('/raid/join', { method: 'POST' });
      var data = await res.json();
      if (data.status !== 'success') return;
      this._joined = true;
      if (this._latest) this._latest.participant_count = data.participant_count;
      var count = document.getElementById('raid-modal-participants');
      var btn   = document.getElementById('raid-join-btn');
      if (count) count.textContent = data.participant_count;
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Joined ✓';
      }
    } catch (e) {}
  },

  _RESOURCE_META: {
    fish: ['🐟', 'Fish'], herbs: ['🌿', 'Herbs'], blood_gems: ['💎', 'Blood Gems'],
    bones: ['🦴', 'Bones'], spell_fragments: ['✨', 'Spell Fragments'], ice_blocks: ['🧊', 'Ice Blocks'],
  },

  // data is either resolve_raid()'s payload (from /raid/attack's own response,
  // shown instantly to whoever landed the killing blow) or GET /raid/results'
  // body (fetched by bystanders once their next poll notices the transition).
  // Both share {boss_name, raid_status, leaderboard}, so one renderer covers both.
  showResults: function(data) {
    if (!data || !data.leaderboard || this._resultsShownFor === data.raid_id) return;
    this._resultsShownFor = data.raid_id;

    const overlay = document.getElementById('raid-results-overlay');
    const title   = document.getElementById('raid-results-title');
    const list    = document.getElementById('raid-results-list');
    const prompt  = document.getElementById('raid-results-lootbox-prompt');
    if (!overlay || !title || !list) return;

    const outcome = data.raid_status === 'succeeded' ? 'DEFEATED!' : 'ESCAPED';
    title.textContent = `⚔️ ${data.boss_name || 'The boss'} ${outcome}`;

    let html = '';
    let ownLootboxes = 0;
    const self = this;
    data.leaderboard.forEach(function(entry) {
      const isSelf = typeof CURRENT_USER !== 'undefined' && entry.username === CURRENT_USER;
      const cls = 'raid-results-row' + (entry.rank <= 3 ? ' top3' : '') + (isSelf ? ' self' : '');
      let rewardText = '';
      if (entry.reward && entry.reward.lootboxes) {
        rewardText = `🎁 x${entry.reward.lootboxes} Lootbox${entry.reward.lootboxes === 1 ? '' : 'es'}`;
        if (isSelf) ownLootboxes = entry.reward.lootboxes;
      } else if (entry.reward && entry.reward.resource_type) {
        const meta = self._RESOURCE_META[entry.reward.resource_type] || ['🎁', entry.reward.resource_type];
        rewardText = `${meta[0]} +${entry.reward.resource_amount} ${meta[1]}`;
      }
      html += `<div class="${cls}">
        <span class="raid-results-rank">#${entry.rank}</span>
        <span class="raid-results-name">${entry.username}${isSelf ? ' (you)' : ''}</span>
        <span class="raid-results-reward">${rewardText}</span>
      </div>`;
    });
    list.innerHTML = html || '<div class="inv-empty">No one joined the fight this time.</div>';

    if (prompt) prompt.style.display = ownLootboxes > 0 ? 'block' : 'none';
    const promptText = document.getElementById('raid-results-lootbox-text');
    if (promptText) promptText.textContent = `You won ${ownLootboxes} lootbox${ownLootboxes === 1 ? '' : 'es'}!`;

    overlay.classList.add('show');
    if (window.GameSounds) GameSounds.modalOpen();
  },

  closeResults: function() {
    const overlay = document.getElementById('raid-results-overlay');
    if (overlay) overlay.classList.remove('show');
    if (window.GameSounds) GameSounds.modalClose();
    if (typeof refreshStats === 'function') refreshStats();
  },

  // Reuses Phase 4's inventory/open flow directly — jumps straight to the
  // Lootboxes tab rather than reimplementing the open animation here.
  openLootboxesNow: function() {
    this.closeResults();
    if (typeof window.openInventory === 'function') {
      window.openInventory().then(function() {
        if (typeof window.switchInvTab === 'function') window.switchInvTab('lootboxes');
      });
    }
  },
};

(function() {
  function hookTabChange() {
    if (typeof switchContentTab !== 'function') return;
    var _origSwitch = switchContentTab;
    switchContentTab = function(name, btn) {
      _origSwitch(name, btn);
      RaidJoin.onTabChange(name);
    };
  }
  document.addEventListener('DOMContentLoaded', function() {
    hookTabChange();
    RaidJoin.startPolling();
  });
})();

window.RaidJoin = RaidJoin;
