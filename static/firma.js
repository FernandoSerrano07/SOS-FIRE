// Captura de firma con el dedo sobre un <canvas>; se guarda como PNG (data-URL).
document.querySelectorAll('.firma-caja').forEach(caja => {
  const canvas = caja.querySelector('canvas');
  const campo = document.querySelector(`input[name="${canvas.dataset.campo}"]`);
  const previa = caja.querySelector('.firma-previa');
  const ctx = canvas.getContext('2d');
  let dibujando = false, tieneTrazo = false;

  const ajustar = () => {
    const r = canvas.getBoundingClientRect(), k = window.devicePixelRatio || 1;
    canvas.width = r.width * k; canvas.height = r.height * k;
    ctx.scale(k, k);
    ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#111';
  };
  ajustar();

  const pos = e => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  canvas.addEventListener('pointerdown', e => {
    dibujando = true; canvas.setPointerCapture(e.pointerId);
    if (previa) previa.hidden = true;
    ctx.beginPath(); ctx.moveTo(...pos(e));
  });
  canvas.addEventListener('pointermove', e => {
    if (!dibujando) return;
    ctx.lineTo(...pos(e)); ctx.stroke(); tieneTrazo = true;
  });
  const fin = () => { if (dibujando && tieneTrazo) campo.value = canvas.toDataURL('image/png'); dibujando = false; };
  canvas.addEventListener('pointerup', fin);
  canvas.addEventListener('pointercancel', fin);
  caja.querySelector('.limpiar').addEventListener('click', () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height); campo.value = ''; tieneTrazo = false;
    if (previa) previa.hidden = true;
  });
});
