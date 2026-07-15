// main.js — students will add JavaScript here as features are built

(function () {
  const form      = document.getElementById('filter-form');
  if (!form) return;

  const fromInput = document.getElementById('filter-from');
  const toInput   = document.getElementById('filter-to');
  const chips     = document.querySelectorAll('.filter-chip[data-preset]');

  const pad = n => String(n).padStart(2, '0');
  const fmt = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  function presetRange(preset) {
    const to = fmt(today);
    if (preset === 'all')     return ['', ''];
    if (preset === 'month')   return [fmt(new Date(today.getFullYear(), today.getMonth(), 1)), to];
    if (preset === '3months') {
      const d = new Date(today);
      d.setMonth(d.getMonth() - 3);
      return [fmt(d), to];
    }
    if (preset === 'year')    return [`${today.getFullYear()}-01-01`, to];
    return ['', ''];
  }

  chips.forEach(chip => {
    chip.addEventListener('click', function () {
      const [from, to] = presetRange(this.dataset.preset);
      fromInput.value = from;
      toInput.value   = to;
      form.submit();
    });
  });

  function markActive() {
    chips.forEach(chip => {
      const [from, to] = presetRange(chip.dataset.preset);
      chip.classList.toggle(
        'filter-chip--active',
        fromInput.value === from && toInput.value === to
      );
    });
  }

  markActive();
})();
