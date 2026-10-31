// Lógica de la pantalla de inspección: marcar ✓/✕/N/A, comentarios,
// guardado automático y cola sin conexión (se reenvía cuando vuelve la señal).
(() => {
  const I = window.INSP;
  const CLAVE_COLA = `sosfire-cola-${I.id}`;
  const lista = document.getElementById('equipos');
  const estadoRed = document.getElementById('estado-red');
  let cola = JSON.parse(localStorage.getItem(CLAVE_COLA) || '{}');
  let enviando = false;
  let filtro = 'todos';

  const leer = li => {
    const valores = {};
    li.querySelectorAll('.criterio').forEach(c => {
      const sel = c.querySelector('.seg.sel');
      if (sel) valores[c.dataset.criterio] = sel.dataset.valor;
    });
    return { valores, comentario: li.querySelector('.comentario').value };
  };

  const pintar = li => {
    const { valores } = leer(li);
    const n = Object.keys(valores).length;
    li.classList.toggle('completo', n >= I.criterios.length);
    li.classList.toggle('hallazgo', Object.values(valores).includes('falta'));
    li.classList.toggle('parcial', n > 0 && n < I.criterios.length);
  };

  const mostrarRed = () => {
    const pendientes = Object.keys(cola).length;
    estadoRed.textContent = pendientes ? `⏳ ${pendientes} sin enviar` : '✓ guardado';
    estadoRed.className = 'estado-red ' + (pendientes ? 'pendiente' : 'ok');
  };

  const actualizarResumen = r => {
    document.getElementById('c-rev').textContent = r.revisados;
    document.getElementById('c-hall').textContent = r.hallazgos;
    document.getElementById('barra').style.width = r.pct + '%';
  };

  async function vaciarCola() {
    if (enviando) return;
    enviando = true;
    try {
      for (const id of Object.keys(cola)) {
        const datos = cola[id];
        const resp = await fetch(I.url + id, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(datos),
        });
        if (resp.status === 401) { location.href = '/login?next=' + location.pathname; return; }
        if (!resp.ok && resp.status !== 409) throw new Error(resp.status);
        if (cola[id] === datos) delete cola[id];   // no borrar si cambió mientras se enviaba
        localStorage.setItem(CLAVE_COLA, JSON.stringify(cola));
        if (resp.ok) actualizarResumen((await resp.json()).resumen);
      }
    } catch (e) {
      setTimeout(vaciarCola, 5000);  // sin señal: reintentar luego
    } finally {
      enviando = false;
      mostrarRed();
    }
  }

  const guardar = li => {
    cola[li.dataset.id] = leer(li);
    localStorage.setItem(CLAVE_COLA, JSON.stringify(cola));
    mostrarRed();
    vaciarCola();
  };

  // Restaurar cambios que quedaron sin enviar (p. ej. se cerró la pestaña sin señal)
  for (const [id, datos] of Object.entries(cola)) {
    const li = lista.querySelector(`.equipo[data-id="${id}"]`);
    if (!li) continue;
    li.querySelectorAll('.criterio').forEach(c => {
      c.querySelectorAll('.seg').forEach(b => b.classList.toggle('sel', datos.valores[c.dataset.criterio] === b.dataset.valor));
    });
    li.querySelector('.comentario').value = datos.comentario || '';
  }
  lista.querySelectorAll('.equipo').forEach(pintar);
  mostrarRed();
  if (Object.keys(cola).length) vaciarCola();
  window.addEventListener('online', vaciarCola);

  if (I.cerrada) return;

  let temporizador;
  lista.addEventListener('click', e => {
    const li = e.target.closest('.equipo');
    if (!li) return;
    const seg = e.target.closest('.seg');
    if (seg) {
      const yaSel = seg.classList.contains('sel');
      seg.parentElement.querySelectorAll('.seg').forEach(b => b.classList.remove('sel'));
      if (!yaSel) seg.classList.add('sel');
      if (seg.dataset.valor === 'falta' && !yaSel) li.querySelector('.comentario').classList.remove('oculto');
      pintar(li); guardar(li); return;
    }
    if (e.target.closest('.todo-ok')) {
      li.querySelectorAll('.criterio').forEach(c => c.querySelectorAll('.seg').forEach(b => b.classList.toggle('sel', b.dataset.valor === 'ok')));
      pintar(li); guardar(li);
      // saltar al siguiente pendiente visible
      let sig = li.nextElementSibling;
      while (sig && (sig.hidden || sig.classList.contains('completo'))) sig = sig.nextElementSibling;
      if (sig) sig.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    if (e.target.closest('.ver-com')) {
      const t = li.querySelector('.comentario');
      t.classList.toggle('oculto');
      if (!t.classList.contains('oculto')) t.focus();
    }
  });
  lista.addEventListener('input', e => {
    if (!e.target.classList.contains('comentario')) return;
    const li = e.target.closest('.equipo');
    clearTimeout(temporizador);
    temporizador = setTimeout(() => guardar(li), 700);
  });

  // Búsqueda y filtros
  const buscar = document.getElementById('buscar');
  const aplicarFiltro = () => {
    const q = buscar.value.trim().toLowerCase();
    lista.querySelectorAll('.equipo').forEach(li => {
      let ver = !q || li.dataset.texto.includes(q);
      if (filtro === 'pendientes') ver = ver && !li.classList.contains('completo');
      if (filtro === 'hallazgos') ver = ver && li.classList.contains('hallazgo');
      li.hidden = !ver;
    });
  };
  buscar.addEventListener('input', aplicarFiltro);
  document.querySelectorAll('.chip').forEach(ch => ch.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach(x => x.classList.remove('activo'));
    ch.classList.add('activo');
    filtro = ch.dataset.filtro;
    aplicarFiltro();
  }));
})();
