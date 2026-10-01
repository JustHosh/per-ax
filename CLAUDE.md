# Smiteless (adaptación LAN) — notas para Claude

Fork independiente de Smiteless (bobbyroylee, MIT) adaptado para jugar en LAN y para cumplir
las políticas de desarrolladores de Riot. Windows, Python (ventanas Tk + tableros renderizados
con PIL), trays en AutoHotkey v2. El usuario habla español: documentación, commits y
respuestas en español; la interfaz de la app sigue en inglés hasta la traducción.

## Reglas que no se rompen (las vigila `tools/selftest.py`)
- **Nada de input simulado.** Ningún módulo usa SendInput / keybd_event / mouse_event /
  SetWindowsHookEx ni `Send` en AHK. La app lee el juego, no lo juega. (check "No input injection")
- **Champ select es del jugador.** Nunca aceptar la cola, banear, lockear ni pedir o aceptar
  swaps por él. Sugerir y hacer hover al hacer clic sí; importar runas sí. (check "No
  champ-select autopilot")
- **Jungla enemiga: solo lo que el juego mostró** (kill feed, anuncios de objetivos, timer de
  muerte). Nada inferido de la niebla, como su CS. (check "Jungle tracker")
- **Nunca desenmascarar jugadores.** En champ select solo se usan nombres de aliados que el
  cliente muestra (`nameVisibilityType` distinto de HIDDEN); nunca el endpoint de
  participantes del chat. (check "Champ-select scout")
- **La nota de un jugador es su rendimiento en partida.** Las etiquetas citan su evidencia
  ([docs/TAGS.md](docs/TAGS.md), `tools/tagcheck.py`).
- Nada de anuncios dentro del juego ni de timers de habilidades enemigas.

## Dónde vive cada cosa
- `core/` lógica, `ui/` ventanas, `tools/` utilidades; `smiteless_main.py` es la entrada única
  del exe congelado.
- `core/smitepaths.py`: todas las rutas. Los datos van en `%APPDATA%\Smiteless`, nunca en el
  repo ni en `~/.claude`. Los trays AHK escriben la misma carpeta a mano.
- `core/smiteconfig.py`: ajustes, `REGIONS` y `region()` / `routing()` (LAN por defecto).
- Clave de Riot: `lolscout.read_key()` / `save_key()` (RIOT_API_KEY > `.env` > archivo).
- Datos propios: `tools/collector.py` (CLI, match-v5 -> `%APPDATA%\Smiteless\matches.sqlite`) y
  `core/lolrecommend.py` (esquema + recomendador fase 1). `lolitems.data_pick()` es el único
  punto donde el widget lo consulta. Nunca guardar nombres ni PUUIDs de los jugadores de esas
  partidas (el check "Match collector" lo vigila).
- Updater: `REPO` en `tools/smiteupdate.py` y `UPDATE_REPO` en `dist/tray.ahk`. Vacíos =
  apagado. Solo se apuntan a un repo propio con releases que lleven `SmitelessSetup.exe`.
- Módulo nuevo en `core/` o `ui/`: agrégalo a `$hidden` en `dist/build.ps1` (el selftest falla
  si falta; PyInstaller no ve los imports perezosos).

## Verificar antes de dar algo por hecho
- `python tools\selftest.py`: todo OK; los "skip" (sin clave, sin cliente, sin CLI de Claude)
  son normales.
- Cambios de interfaz: renderizar con datos y mirar el PNG (skill `verify`,
  `python tools\uishot.py`).
- En esta PC no hay AutoHotkey: los cambios a `.ahk` deben ser mínimos y revisados a mano.
- No manejar en vivo lo destructivo (`lolaccounts.switch` cierra los clientes de Riot) ni
  POSTs a la LCU a mitad de cola.

## Upstream
`upstream` apunta al repo original (push bloqueado). Para traer un arreglo: `git fetch upstream`
y `git cherry-pick <hash>`. Nunca `git merge upstream/main`: reintroduce lo que se quitó.
