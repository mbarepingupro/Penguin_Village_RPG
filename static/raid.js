const RaidJoin = {
  _polling: null,
  _onMapTab: false,
  _joined: false,
  _latest: null,

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
      if (!icon) return;
      icon.classList.toggle('show', data.status === 'join_window');
      if (data.status === 'join_window') this._renderModal(data);
    } catch (e) {}
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
