const RaidJoin = {
  _polling: null,
  _onMapTab: false,
  _joined: false,
  _latest: null,
  _lastStatus: null,
  _lastRaidId: null,
  _resultsShownFor: null,   // raid_id we've already popped the results modal for
  _countdownTimer: null,    // 1s local tick between /raid/status polls
  _joinWindowEnd: null,     // epoch seconds, re-synced from the server each poll

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
      if (data.status === 'join_window') {
        this._renderModal(data);
        if (data.join_window_end) this._startCountdown(data.join_window_end);
      } else {
        this._stopCountdown();
      }

      // The boss HP bar and the weekly challenge bar share the same overlay
      // slot — exactly one of them is ever shown, matching the status value.
      // The leaderboard button is a separate element, but only ever visible
      // alongside the boss bar (same condition, not inside it).
      var bossBar = document.getElementById('raid-boss-bar');
      var wcBar   = document.getElementById('weekly-challenge-bar');
      var lbBtn   = document.getElementById('raid-leaderboard-btn');

      if (data.status === 'active') {
        if (wcBar) wcBar.classList.remove('show');
        if (bossBar) {
          bossBar.classList.add('show');
          var nameEl = document.getElementById('raid-boss-name');
          if (nameEl) nameEl.textContent = '⚔️ ' + (data.boss_name || 'Raid Boss');
        }
        if (lbBtn) lbBtn.classList.add('show');
        if (window.BuildAttackButton) window.BuildAttackButton.setAttackMode(true);
        this.updateBossBar(data.boss_current_hp, data.boss_max_hp);
        this._lastRaidId = data.raid_id;
      } else {
        if (bossBar) bossBar.classList.remove('show');
        if (lbBtn) lbBtn.classList.remove('show');
        if (window.BuildAttackButton) window.BuildAttackButton.setAttackMode(false);
        // Bystanders (didn't land the killing blow) find out the raid ended
        // here, up to 30s later — whoever attacked last already saw the
        // results modal instantly via /raid/attack's own response.
        if (this._lastStatus === 'active' && this._lastRaidId) {
          this._fetchAndShowResults(this._lastRaidId);
        }

        if (data.status === 'challenge_active') {
          this.updateChallengeBar(data);
        } else if (wcBar) {
          wcBar.classList.remove('show');
        }
      }
      this._lastStatus = data.status;
    } catch (e) {}
  },

  updateChallengeBar: function(data) {
    var wcBar = document.getElementById('weekly-challenge-bar');
    var label = document.getElementById('weekly-challenge-label');
    var fill  = document.getElementById('weekly-challenge-fill');
    var text  = document.getElementById('weekly-challenge-text');
    if (!wcBar) return;
    wcBar.classList.add('show');
    var pct = data.threshold > 0
      ? Math.max(0, Math.min(100, Math.round((data.current_progress / data.threshold) * 100)))
      : 0;
    if (label) label.textContent = '🏆 Weekly Challenge — Unlocks Weekend Raid';
    if (fill)  fill.style.width = pct + '%';
    if (text) {
      text.textContent = (data.metric_label || data.metric_type || 'Progress') + ': ' +
        (data.current_progress || 0).toLocaleString() + ' / ' + (data.threshold || 0).toLocaleString();
    }
  },

  // Re-synced from the server's join_window_end on every /raid/status poll
  // (every 30s); ticks down locally every second in between so the display
  // doesn't need to hit the server once per second.
  _startCountdown: function(endTs) {
    this._joinWindowEnd = endTs;
    this._tickCountdown();
    if (this._countdownTimer) return;
    var self = this;
    this._countdownTimer = setInterval(function() { self._tickCountdown(); }, 1000);
  },

  _stopCountdown: function() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = null;
    }
    this._joinWindowEnd = null;
    var el = document.getElementById('raid-join-countdown');
    if (el) el.textContent = '';
  },

  _tickCountdown: function() {
    var el = document.getElementById('raid-join-countdown');
    if (!el || !this._joinWindowEnd) return;
    var remaining = Math.floor(this._joinWindowEnd - Date.now() / 1000);
    if (remaining <= 0) {
      // Clamp at zero rather than counting negative -- the icon itself
      // disappears on the next /raid/status poll (up to 30s later), same
      // as every other status-driven overlay element.
      el.textContent = 'Starts in: 0:00';
      if (this._countdownTimer) { clearInterval(this._countdownTimer); this._countdownTimer = null; }
      return;
    }
    el.textContent = 'Starts in: ' + this._formatCountdown(remaining);
  },

  _formatCountdown: function(totalSeconds) {
    var h = Math.floor(totalSeconds / 3600);
    var m = Math.floor((totalSeconds % 3600) / 60);
    var s = totalSeconds % 60;
    if (h > 0) return h + 'h ' + m + 'm';
    if (m > 0) return m + 'm ' + (s < 10 ? '0' : '') + s + 's';
    return s + 's';
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

  openLootInfo: function() {
    var overlay = document.getElementById('raid-loot-info-overlay');
    if (overlay) overlay.classList.add('show');
    if (window.GameSounds) GameSounds.modalOpen();
  },

  closeLootInfo: function() {
    var overlay = document.getElementById('raid-loot-info-overlay');
    if (overlay) overlay.classList.remove('show');
    if (window.GameSounds) GameSounds.modalClose();
  },

  // Live, in-progress leaderboard — reuses GET /raid/results (Phase 5), which
  // now also accepts an 'active' raid instead of only resolved ones. Rewards
  // come back empty ({}) since nothing's been decided yet; we only show rank/
  // username/damage here.
  openLeaderboard: async function() {
    var raidId = this._lastRaidId || (this._latest && this._latest.raid_id);
    if (!raidId) return;
    var overlay = document.getElementById('raid-leaderboard-overlay');
    var list    = document.getElementById('raid-leaderboard-list');
    if (!overlay || !list) return;
    list.innerHTML = '<div class="inv-empty">Loading…</div>';
    overlay.classList.add('show');
    if (window.GameSounds) GameSounds.modalOpen();
    try {
      var res  = await fetch('/raid/results/' + raidId);
      var data = await res.json();
      if (data.status !== 'success' || !data.leaderboard) {
        list.innerHTML = '<div class="inv-empty">Leaderboard unavailable.</div>';
        return;
      }
      var html = '';
      data.leaderboard.forEach(function(entry) {
        var isSelf = typeof CURRENT_USER !== 'undefined' && entry.username === CURRENT_USER;
        var cls = 'raid-results-row' + (entry.rank <= 3 ? ' top3' : '') + (isSelf ? ' self' : '');
        html += '<div class="' + cls + '">' +
          '<span class="raid-results-rank">#' + entry.rank + '</span>' +
          '<span class="raid-results-name">' + entry.username + (isSelf ? ' (you)' : '') + '</span>' +
          '<span class="raid-results-reward" style="color:#FF8C00;">' + entry.total_damage_dealt.toLocaleString() + ' dmg</span>' +
          '</div>';
      });
      list.innerHTML = html || '<div class="inv-empty">No one has joined the fight yet.</div>';
    } catch (e) {
      list.innerHTML = '<div class="inv-empty">Leaderboard unavailable.</div>';
    }
  },

  closeLeaderboard: function() {
    var overlay = document.getElementById('raid-leaderboard-overlay');
    if (overlay) overlay.classList.remove('show');
    if (window.GameSounds) GameSounds.modalClose();
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
    // /raid/status's "joined" field is the server-verified source of truth --
    // covers a second device/session that already joined elsewhere, not just
    // this browser's own local _joined flag from a prior click here.
    if (data.joined) this._joined = true;
    if (btn) {
      if (this._joined) {
        btn.disabled = true;
        btn.textContent = 'Joined ✓';
      } else {
        btn.disabled = false;
        btn.textContent = 'Join Raid';
      }
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
        rewardText = `🎁 x${entry.reward.lootboxes} N00Tbox${entry.reward.lootboxes === 1 ? '' : 'es'}`;
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
    if (promptText) promptText.textContent = `You won ${ownLootboxes} N00Tbox${ownLootboxes === 1 ? '' : 'es'}!`;

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
