# 🔥 SOS FIRE · Inspecciones digitales

Aplicación web (Python + Flask + PostgreSQL) para llenar desde el teléfono los
formatos de inspección que antes se hacían a mano en Excel:

- **Lámparas de emergencia** (205 equipos): Estado general · Iluminación · Conexión · Estado físico
- **Detectores de humo** (239 equipos): Estado general · Batería · Completo/Integridad · Estado físico
- **Alarmas de emergencia** (89 equipos): Estado general · Activación/Prueba · Completo · Estado físico

Los equipos se cargaron del archivo `FORMATO DE INSPECCIÓN DECAMERON 2026.xlsx`
(ver `data/equipos_decameron.json`) la primera vez que arranca la app.

## Qué hace

- Crear una inspección (tipo, fecha, técnico, encargado).
- Por cada equipo, tocar **✓ / ✕ / N/A** en cada criterio, o **✓ Todo OK** de un toque
  (salta solo al siguiente equipo pendiente).
- Comentarios por equipo (se abren solos al marcar ✕).
- **Guardado automático**. Si se va la señal, los cambios quedan en el teléfono y se
  envían solos al volver la conexión.
- Buscar por ubicación o N°, y filtrar *Pendientes* / *Con ✕*.
- **Firmas con el dedo** (técnico y encargado) y finalizar la inspección.
- **Descargar a Excel** con el mismo formato (✓ ✕ N/A, comentarios, firmas).
- Catálogo de equipos: agregar, corregir o desactivar equipos.
- Se puede "instalar" en el teléfono (Agregar a pantalla de inicio).

## Probar en tu computadora

```bash
pip install -r requirements.txt
python app.py
```

Abre http://localhost:5000. Sin `DATABASE_URL` usa un archivo SQLite local para pruebas.
Para usar PostgreSQL:

```bash
export DATABASE_URL=postgresql://usuario:clave@localhost/sosfire
```

## Publicar en internet (Render, gratis)

1. Entra a https://render.com con tu cuenta de GitHub.
2. **New → Blueprint** y elige este repositorio. Render lee `render.yaml` y crea
   la app web **y** la base de datos PostgreSQL automáticamente.
3. Cuando te pida `APP_PASSWORD`, escribe la clave que usarán los técnicos para entrar.
4. Abre la dirección que te da Render desde el teléfono y agrégala a la pantalla de inicio.

## Variables de entorno

| Variable       | Para qué                                                   |
|----------------|------------------------------------------------------------|
| `DATABASE_URL` | Conexión a PostgreSQL (Render la pone sola).                |
| `APP_PASSWORD` | Clave para entrar. Si no se define, la app queda abierta.   |
| `SECRET_KEY`   | Clave para las sesiones (Render la genera sola).            |
