---
name: verify
description: Cómo comprobar y ver los cambios de Per-Ax (adaptación LAN) en esta PC sin cliente de League ni partida.
---

# Verificar Per-Ax

Repo: `C:\Users\luang\Downloads\smiteless-main`. Cada ventana se puede abrir sola (las rutas se
resuelven con los `sys.path.insert` de cada archivo):

    python perax_main.py <overlay|widget|settings|profile|queue|load|dead|notes>

## 1. Salud general

    python tools\selftest.py

Debe salir todo OK. Los "skip" esperados: sin clave de Riot, cliente de League cerrado y sin el
CLI de Claude. Las comprobaciones de políticas (input simulado, piloto automático de champ
select, jungla, desenmascarar jugadores, silencio sin teclado) nunca deben fallar.

Para detectar nombres rotos después de borrar código: pyflakes en un venv temporal (no en el
Python del usuario) y comparar contra el commit anterior; el original ya trae unas 20
advertencias.

## 2. Ver la interfaz

    python tools\uishot.py [settings] [champselect] [widget] [draftboard] [--out DIR]

- `champselect` y `widget` se dibujan con datos de demo a través de las funciones reales
  (`smitecard.render_cs_vertical`, `smitewidget._render_body`).
- `settings` abre la ventana Tk real invisible (alpha 0, sin robar el foco) y la captura con
  PrintWindow, una vista por desplazamiento.
- `draftboard` es `docs/draft/index.html#demo` en Edge headless.

Mira los PNG (salen en `%APPDATA%\Per-Ax\cache\uishot`). Un cambio de color sin captura no
cuenta como verificado.

## 3. Lo que no se puede probar aquí

- **AutoHotkey no está instalado.** `perax.ahk`, `dist/tray.ahk` y `dist/installer.ahk` no
  se pueden validar: cambios mínimos, sintaxis v2 simple y revisión a mano.
- Sin cliente ni partida no corren la LCU ni `:2999`: prueba las funciones puras con fixtures
  o con sesiones falsas (como hacen los checks del selftest), no en vivo.
- Nunca ejecutar lo destructivo: `lolaccounts.switch` cierra los clientes de Riot, y los POST
  a la LCU actúan sobre una cola o champ select real.
- Nunca SetForegroundWindow ni clics simulados: el usuario puede estar en partida.
