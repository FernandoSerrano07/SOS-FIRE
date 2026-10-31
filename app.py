"""SOS FIRE · Inspecciones digitales de equipos contra incendio.

Aplicación web (Flask + PostgreSQL) para llenar desde el teléfono los formatos
de inspección de lámparas de emergencia, detectores de humo y alarmas.
"""
import base64
import io
import json
import os
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func

BASE_DIR = Path(__file__).resolve().parent
SEED_FILE = BASE_DIR / "data" / "equipos_decameron.json"

VALORES = {"ok": "✓", "falta": "✕", "na": "N/A"}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        if os.environ.get("RENDER"):
            raise RuntimeError("Falta la variable DATABASE_URL (conexión a PostgreSQL).")
        return f"sqlite:///{BASE_DIR / 'sosfire_local.db'}"
    # Render/Heroku entregan "postgres://"; SQLAlchemy necesita el driver explícito.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = _database_url()
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 días en el teléfono
db = SQLAlchemy(app)


# ───────────────────────────── Modelos ─────────────────────────────

class Proyecto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, unique=True)
    tipos = db.relationship("TipoEquipo", backref="proyecto", order_by="TipoEquipo.orden")


class TipoEquipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey("proyecto.id"), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)        # LÁMPARAS
    titulo = db.Column(db.String(200), nullable=False)       # LÁMPARAS DE EMERGENCIA
    criterios = db.Column(db.JSON, nullable=False)           # ["ESTADO GENERAL", ...]
    orden = db.Column(db.Integer, default=0)
    equipos = db.relationship("Equipo", backref="tipo", order_by="Equipo.numero")


class Equipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo_id = db.Column(db.Integer, db.ForeignKey("tipo_equipo.id"), nullable=False)
    numero = db.Column(db.Integer, nullable=False)
    zona = db.Column(db.String(120), default="")
    ubicacion = db.Column(db.String(250), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)


class Inspeccion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo_id = db.Column(db.Integer, db.ForeignKey("tipo_equipo.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    tecnico = db.Column(db.String(150), nullable=False)
    encargado = db.Column(db.String(150), default="")
    firma_tecnico = db.Column(db.Text)       # imagen PNG en data-URL
    firma_encargado = db.Column(db.Text)
    estado = db.Column(db.String(20), default="borrador", nullable=False)  # borrador | finalizada
    creada = db.Column(db.DateTime, default=datetime.utcnow)
    tipo = db.relationship("TipoEquipo")
    resultados = db.relationship("Resultado", backref="inspeccion", cascade="all, delete-orphan")


class Resultado(db.Model):
    __table_args__ = (UniqueConstraint("inspeccion_id", "equipo_id"),)
    id = db.Column(db.Integer, primary_key=True)
    inspeccion_id = db.Column(db.Integer, db.ForeignKey("inspeccion.id"), nullable=False)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipo.id"), nullable=False)
    valores = db.Column(db.JSON, nullable=False, default=dict)   # {"ESTADO GENERAL": "ok", ...}
    comentario = db.Column(db.Text, default="")
    actualizado = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    equipo = db.relationship("Equipo")


# ───────────────────────────── Datos iniciales ─────────────────────────────

def cargar_datos_iniciales() -> None:
    """Crea las tablas y, si la base está vacía, carga los equipos del Excel original."""
    db.create_all()
    if Proyecto.query.first() or not SEED_FILE.exists():
        return
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    proyecto = Proyecto(nombre=data["proyecto"])
    db.session.add(proyecto)
    for orden, t in enumerate(data["tipos"]):
        tipo = TipoEquipo(proyecto=proyecto, nombre=t["nombre"], titulo=t["titulo"],
                          criterios=t["criterios"], orden=orden)
        db.session.add(tipo)
        for e in t["equipos"]:
            db.session.add(Equipo(tipo=tipo, numero=e["numero"], zona=e.get("zona", ""),
                                  ubicacion=e["ubicacion"]))
    db.session.commit()


with app.app_context():
    cargar_datos_iniciales()


# ───────────────────────────── Acceso ─────────────────────────────

def login_requerido(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if os.environ.get("APP_PASSWORD") and not session.get("ok"):
            if request.path.startswith("/api/"):
                return jsonify(error="sesión expirada"), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return envoltura


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("clave") == os.environ.get("APP_PASSWORD"):
            session.permanent = True
            session["ok"] = True
            if request.form.get("tecnico"):
                session["tecnico"] = request.form["tecnico"].strip()
            destino = request.args.get("next", "")
            return redirect(destino if destino.startswith("/") else url_for("inicio"))
        flash("Clave incorrecta", "error")
    return render_template("login.html")


@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("login"))


@app.route("/salud")
def salud():
    return "ok"


# ───────────────────────────── Utilidades ─────────────────────────────

def resumen(insp: Inspeccion) -> dict:
    """Cuenta equipos revisados y equipos con hallazgos (alguna ✕)."""
    total = Equipo.query.filter_by(tipo_id=insp.tipo_id, activo=True).count()
    n_crit = len(insp.tipo.criterios)
    revisados = hallazgos = 0
    for r in insp.resultados:
        vals = r.valores or {}
        if len([v for v in vals.values() if v]) >= n_crit:
            revisados += 1
        if "falta" in vals.values():
            hallazgos += 1
    return {"total": total, "revisados": revisados, "hallazgos": hallazgos,
            "pct": round(100 * revisados / total) if total else 0}


def obtener_inspeccion(insp_id: int) -> Inspeccion:
    insp = db.session.get(Inspeccion, insp_id)
    if not insp:
        abort(404)
    return insp


# ───────────────────────────── Inspecciones ─────────────────────────────

@app.route("/")
@login_requerido
def inicio():
    inspecciones = Inspeccion.query.order_by(Inspeccion.fecha.desc(), Inspeccion.id.desc()).limit(100).all()
    proyecto = Proyecto.query.first()
    return render_template("inicio.html", inspecciones=inspecciones, proyecto=proyecto,
                           resumen=resumen)


@app.route("/inspeccion/nueva", methods=["GET", "POST"])
@login_requerido
def nueva_inspeccion():
    tipos = TipoEquipo.query.order_by(TipoEquipo.orden).all()
    if request.method == "POST":
        tipo = db.session.get(TipoEquipo, request.form.get("tipo_id", type=int) or 0)
        tecnico = request.form.get("tecnico", "").strip()
        if not tipo or not tecnico:
            flash("Elige el tipo de equipo y escribe el nombre del técnico.", "error")
        else:
            try:
                fecha = date.fromisoformat(request.form.get("fecha", ""))
            except ValueError:
                fecha = date.today()
            insp = Inspeccion(tipo=tipo, fecha=fecha, tecnico=tecnico,
                              encargado=request.form.get("encargado", "").strip())
            db.session.add(insp)
            db.session.commit()
            session["tecnico"] = tecnico
            return redirect(url_for("ver_inspeccion", insp_id=insp.id))
    return render_template("nueva.html", tipos=tipos, hoy=date.today().isoformat(),
                           tecnico=session.get("tecnico", ""),
                           tipo_sel=request.args.get("tipo", type=int))


@app.route("/inspeccion/<int:insp_id>")
@login_requerido
def ver_inspeccion(insp_id):
    insp = obtener_inspeccion(insp_id)
    equipos = Equipo.query.filter_by(tipo_id=insp.tipo_id, activo=True).order_by(Equipo.numero).all()
    resultados = {r.equipo_id: {"valores": r.valores or {}, "comentario": r.comentario or ""}
                  for r in insp.resultados}
    return render_template("inspeccion.html", insp=insp, equipos=equipos,
                           resultados=resultados, resumen=resumen(insp))


@app.route("/api/inspeccion/<int:insp_id>/equipo/<int:equipo_id>", methods=["POST"])
@login_requerido
def guardar_resultado(insp_id, equipo_id):
    insp = obtener_inspeccion(insp_id)
    if insp.estado == "finalizada":
        return jsonify(error="La inspección ya está finalizada"), 409
    equipo = db.session.get(Equipo, equipo_id)
    if not equipo or equipo.tipo_id != insp.tipo_id:
        abort(404)
    datos = request.get_json(silent=True) or {}
    valores = {c: v for c, v in (datos.get("valores") or {}).items()
               if c in insp.tipo.criterios and v in VALORES}
    res = Resultado.query.filter_by(inspeccion_id=insp.id, equipo_id=equipo.id).first()
    if not res:
        res = Resultado(inspeccion_id=insp.id, equipo_id=equipo.id)
        db.session.add(res)
    res.valores = valores
    res.comentario = str(datos.get("comentario", ""))[:2000]
    res.actualizado = datetime.utcnow()
    db.session.commit()
    return jsonify(ok=True, resumen=resumen(insp))


@app.route("/inspeccion/<int:insp_id>/datos", methods=["POST"])
@login_requerido
def editar_datos(insp_id):
    insp = obtener_inspeccion(insp_id)
    try:
        insp.fecha = date.fromisoformat(request.form.get("fecha", ""))
    except ValueError:
        pass
    insp.tecnico = request.form.get("tecnico", insp.tecnico).strip() or insp.tecnico
    insp.encargado = request.form.get("encargado", insp.encargado).strip()
    db.session.commit()
    flash("Datos guardados", "ok")
    return redirect(url_for("ver_inspeccion", insp_id=insp.id))


@app.route("/inspeccion/<int:insp_id>/firmar", methods=["GET", "POST"])
@login_requerido
def firmar(insp_id):
    insp = obtener_inspeccion(insp_id)
    if request.method == "POST":
        for campo in ("firma_tecnico", "firma_encargado"):
            valor = request.form.get(campo, "")
            if valor.startswith("data:image/png;base64,"):
                setattr(insp, campo, valor)
        if request.form.get("encargado"):
            insp.encargado = request.form["encargado"].strip()
        if request.form.get("accion") == "finalizar":
            if not insp.firma_tecnico:
                flash("Falta la firma del técnico.", "error")
                db.session.commit()
                return redirect(url_for("firmar", insp_id=insp.id))
            insp.estado = "finalizada"
        db.session.commit()
        flash("Inspección finalizada ✓" if insp.estado == "finalizada" else "Firmas guardadas", "ok")
        return redirect(url_for("ver_inspeccion", insp_id=insp.id))
    return render_template("firmar.html", insp=insp, resumen=resumen(insp))


@app.route("/inspeccion/<int:insp_id>/reabrir", methods=["POST"])
@login_requerido
def reabrir(insp_id):
    insp = obtener_inspeccion(insp_id)
    insp.estado = "borrador"
    db.session.commit()
    return redirect(url_for("ver_inspeccion", insp_id=insp.id))


@app.route("/inspeccion/<int:insp_id>/eliminar", methods=["POST"])
@login_requerido
def eliminar(insp_id):
    insp = obtener_inspeccion(insp_id)
    db.session.delete(insp)
    db.session.commit()
    flash("Inspección eliminada", "ok")
    return redirect(url_for("inicio"))


# ───────────────────────────── Exportar a Excel ─────────────────────────────

@app.route("/inspeccion/<int:insp_id>/excel")
@login_requerido
def exportar_excel(insp_id):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    insp = obtener_inspeccion(insp_id)
    tipo = insp.tipo
    criterios = tipo.criterios
    resultados = {r.equipo_id: r for r in insp.resultados}
    equipos = Equipo.query.filter_by(tipo_id=tipo.id, activo=True).order_by(Equipo.numero).all()

    wb = Workbook()
    ws = wb.active
    ws.title = tipo.nombre[:31]
    ultima = 3 + len(criterios) + 1          # columna de comentarios
    col_com = ultima
    rojo = PatternFill("solid", fgColor="C62828")
    gris = PatternFill("solid", fgColor="EEEEEE")
    blanco_b = Font(bold=True, color="FFFFFF")
    fino = Side(style="thin", color="999999")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def fila_fusionada(fila, texto, **estilo):
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ultima)
        c = ws.cell(fila, 1, texto)
        for k, v in estilo.items():
            setattr(c, k, v)

    fila_fusionada(1, f"{tipo.proyecto.nombre} · SOS FIRE", font=Font(bold=True, size=14, color="C62828"),
                   alignment=centro)
    fila_fusionada(2, f"FORMATO DE INSPECCIÓN · {tipo.titulo}", font=Font(bold=True, size=12), alignment=centro)
    fila_fusionada(3, "Marcación: ✓ = OK · ✕ = Falta · N/A = No aplica. Ampliar cualquier hallazgo en COMENTARIOS.",
                   font=Font(italic=True, size=9))
    ws.cell(4, 1, f"Fecha de inspección: {insp.fecha.strftime('%d/%m/%Y')}").font = Font(bold=True)
    ws.cell(4, 3, f"Nombre técnico SOS FIRE: {insp.tecnico}").font = Font(bold=True)
    ws.cell(4, col_com - 1, "Firma técnico:").font = Font(bold=True)
    ws.cell(5, 1, f"Nombre del encargado: {insp.encargado or ''}").font = Font(bold=True)
    ws.cell(5, col_com - 1, "Firma encargado:").font = Font(bold=True)

    encabezados = ["N°", "ZONA", "UBICACIÓN", *criterios, "COMENTARIOS"]
    for i, h in enumerate(encabezados, start=1):
        c = ws.cell(7, i, h)
        c.fill, c.font, c.alignment, c.border = rojo, blanco_b, centro, borde

    fila = 8
    for eq in equipos:
        r = resultados.get(eq.id)
        vals = (r.valores if r else {}) or {}
        datos = [eq.numero, eq.zona, eq.ubicacion,
                 *[VALORES.get(vals.get(c, ""), "") for c in criterios],
                 (r.comentario if r else "") or ""]
        for i, v in enumerate(datos, start=1):
            c = ws.cell(fila, i, v)
            c.border = borde
            c.alignment = centro if 3 < i < col_com or i == 1 else Alignment(vertical="center", wrap_text=True)
            if v == "✕":
                c.font = Font(bold=True, color="C62828")
            elif v == "✓":
                c.font = Font(color="2E7D32")
        if "falta" in vals.values():
            for i in (1, 2, 3):
                ws.cell(fila, i).fill = PatternFill("solid", fgColor="FDECEA")
        elif fila % 2 == 0:
            for i in range(1, ultima + 1):
                ws.cell(fila, i).fill = gris
        fila += 1

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 42
    for i in range(len(criterios)):
        ws.column_dimensions[chr(ord("D") + i)].width = 14
    ws.column_dimensions[chr(ord("A") + col_com - 1)].width = 45
    ws.row_dimensions[7].height = 32
    ws.freeze_panes = "A8"
    ws.print_title_rows = "7:7"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    _insertar_firmas(ws, insp, col_com)

    salida = io.BytesIO()
    wb.save(salida)
    salida.seek(0)
    nombre = f"Inspeccion_{tipo.nombre}_{insp.fecha.isoformat()}_{insp.id}.xlsx"
    return send_file(salida, as_attachment=True, download_name=nombre,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _insertar_firmas(ws, insp, col_com):
    """Pega las firmas (PNG) al lado de los rótulos de firma, si Pillow está disponible."""
    try:
        from openpyxl.drawing.image import Image as XLImage
    except ImportError:  # pragma: no cover
        return
    letra = chr(ord("A") + col_com - 1)
    ws.row_dimensions[4].height = 40
    ws.row_dimensions[5].height = 40
    for fila, firma in ((4, insp.firma_tecnico), (5, insp.firma_encargado)):
        if not firma:
            continue
        try:
            png = base64.b64decode(firma.split(",", 1)[1])
            img = XLImage(io.BytesIO(png))
            escala = 50 / img.height if img.height else 1
            img.width, img.height = int(img.width * escala), 50
            ws.add_image(img, f"{letra}{fila}")
        except Exception:  # firma dañada: se omite sin romper la descarga
            continue


# ───────────────────────────── Equipos (catálogo) ─────────────────────────────

@app.route("/equipos")
@login_requerido
def equipos_index():
    tipos = TipoEquipo.query.order_by(TipoEquipo.orden).all()
    conteos = dict(db.session.query(Equipo.tipo_id, func.count(Equipo.id))
                   .filter(Equipo.activo.is_(True)).group_by(Equipo.tipo_id).all())
    return render_template("equipos_index.html", tipos=tipos, conteos=conteos)


@app.route("/equipos/<int:tipo_id>", methods=["GET", "POST"])
@login_requerido
def equipos_tipo(tipo_id):
    tipo = db.session.get(TipoEquipo, tipo_id) or abort(404)
    if request.method == "POST":
        ubicacion = request.form.get("ubicacion", "").strip()
        if ubicacion:
            ultimo = db.session.query(func.max(Equipo.numero)).filter_by(tipo_id=tipo.id).scalar() or 0
            numero = request.form.get("numero", type=int) or ultimo + 1
            db.session.add(Equipo(tipo=tipo, numero=numero, ubicacion=ubicacion,
                                  zona=request.form.get("zona", "").strip()))
            db.session.commit()
            flash(f"Equipo N° {numero} agregado", "ok")
        return redirect(url_for("equipos_tipo", tipo_id=tipo.id))
    equipos = Equipo.query.filter_by(tipo_id=tipo.id).order_by(Equipo.activo.desc(), Equipo.numero).all()
    return render_template("equipos_tipo.html", tipo=tipo, equipos=equipos)


@app.route("/equipo/<int:equipo_id>", methods=["POST"])
@login_requerido
def editar_equipo(equipo_id):
    eq = db.session.get(Equipo, equipo_id) or abort(404)
    if request.form.get("accion") == "alternar":
        eq.activo = not eq.activo
    else:
        eq.numero = request.form.get("numero", type=int) or eq.numero
        eq.zona = request.form.get("zona", "").strip()
        eq.ubicacion = request.form.get("ubicacion", "").strip() or eq.ubicacion
    db.session.commit()
    return redirect(url_for("equipos_tipo", tipo_id=eq.tipo_id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
