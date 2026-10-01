# Smiteless — adaptación LAN

Asistente de League of Legends para Windows: te acompaña en champ select, en la pantalla de
carga y durante la partida, y entre partidas te dice qué hábito te está costando LP. Esta es
una versión propia e independiente, adaptada para jugar en **LAN** y para mantenerse dentro de
las [políticas para desarrolladores de Riot](https://developer.riotgames.com/policies/general).

> Proyecto personal, sin garantía. **No está afiliado ni respaldado por Riot Games.**
> League of Legends y Riot Games son marcas de Riot Games, Inc.

## Qué hace

**Champ select**
- Sugerencias de picks para tu rol (counters a lo que ya lockeó el rival y encaje con tu
  equipo) y de bans. Un clic en una sugerencia hace *hover*; lockear y banear siempre lo haces tú.
- Importa runas y hechizos con un botón, o solo al lockear (opcional).
- Scout de tus aliados (rank, racha, nota de rendimiento) solo si el cliente te muestra sus
  nombres.
- **CLIMB MODE**: enciende todas las lecturas y te recuerda tu pool (main + backup).

**Pantalla de carga**
- Scout de los diez jugadores: rank, forma reciente, KDA, maestría y etiquetas que citan su
  evidencia (ver [docs/TAGS.md](docs/TAGS.md)).

**En partida** (todo de solo lectura, desde la API local del juego)
- Widget con timers de objetivos, ventanas de tempo, guardias de los primeros 14 minutos
  (BLEED), del minuto y medio tras reaparecer (RE-ENTRY), de partidas ganadas (CLOSER) y
  perdidas (THE OUT), ritmo de farmeo (GOLD CLOCK), visión (WARD CLOCK) y objetos sugeridos
  según el daño real del rival.
- Resumen al morir (Death Brief) y estado del jungla enemigo **solo con lo que el juego ya te
  mostró**: kill feed, anuncios de objetivos y su timer de muerte.
- Modo silencio: oculta los chats y silencia el audio de pings con los ajustes del propio
  cliente.

**Entre partidas**
- Perfil con tus partidas calificadas, THE ONE FIX (el hábito que más LP te cuesta), THE POOL
  (tus campeones medidos en LP) y QUEUE CALL (si conviene jugar otra).

## Qué cambió respecto al original

| Original | Aquí | Por qué |
|---|---|---|
| Solo NA (`na1`) | Región configurable, **LAN (`la1`)** por defecto | Jugamos en LAN |
| Auto-accept, auto-ban, auto-lock (MAX ELO), swaps automáticos | Eliminados; MAX ELO pasa a CLIMB MODE (solo recordatorio) | Riot prohíbe automatizar decisiones de champ select |
| Auto-mute escribiendo `/fullmute all` con teclado simulado | Solo ajustes del cliente | Prohibido inyectar input en la partida |
| Login con contraseña guardada y autocompletado | Eliminado (queda el cambio de cuenta por sesión, sin contraseñas) | Riesgo de seguridad innecesario |
| Rastreo del jungla deduciendo su posición por el CS | Solo kill feed y timer de muerte | No inferir información oculta por la niebla |
| Nombres de aliados leídos del chat aunque el cliente los oculte | Solo nombres que el cliente muestra | No desanonimizar jugadores |
| Auto-updater desde el repo del autor | Apagado hasta tener releases propios | Ejecutaba código que no revisamos |
| Datos en `~/.claude` (carpeta de Claude Code) | `%APPDATA%\Smiteless` | No mezclar con otras herramientas |

`python tools\selftest.py` incluye comprobaciones que fallan si alguna de esas funciones
regresa (sin input simulado, sin piloto automático de champ select, jungla solo con
información mostrada, sin desenmascarar jugadores).

## Correrlo desde el código

Requisitos: Windows 10/11, Python 3.11+ y League en modo **Sin bordes** (Borderless).

```
pip install -r requirements.txt
python tools\selftest.py              # salud general: debe salir todo OK (los "skip" son opcionales)
python smiteless_main.py settings     # ajustes
python smiteless_main.py profile      # perfil / inicio
python smiteless_main.py overlay      # tablero de champ select / partida
python smiteless_main.py widget       # widget en partida
```

Para que se abra solo en champ select y en partida hace falta la bandeja (tray):

- **Recomendado:** instala [AutoHotkey v2](https://www.autohotkey.com/) y abre `smiteless.ahk`
  (es el mismo tray que lleva el instalador).
- **Sin AutoHotkey:** `pip install pystray` y `pythonw tools\smiteless_tray.py`. Es más
  limitado: solo abre el tablero automáticamente.

Para generar un instalador propio (`SmitelessSetup.exe`) ve [INSTALL.md](INSTALL.md).

## Clave de la API de Riot

El scout, el rank y el historial necesitan tu clave de
[developer.riotgames.com](https://developer.riotgames.com). La app la busca en este orden:

1. La variable de entorno `RIOT_API_KEY`.
2. Un archivo `.env` en la raíz del repo (solo al correr desde el código; está en
   `.gitignore`). Copia `.env.example` a `.env` y pon tu clave.
3. Lo que pegues en **Ajustes → RIOT API KEY** (se guarda en
   `%APPDATA%\Smiteless\riot_api_key.txt`).

Nunca la pongas en un archivo versionado. La clave de desarrollo caduca cada 24 horas y tiene
límites bajos: alcanza para uso personal. Para distribuir la app hay que registrarla en Riot y
pedir una clave de producción.

## Dónde guarda cosas

Todo vive en `%APPDATA%\Smiteless`: `settings.json`, tu historial (behavior ledger y LP),
`logs\` y `cache\` (se puede borrar; se vuelve a descargar).

## Actualizaciones

Apagadas. Cuando publiquemos releases propios, pon `owner/repo` en `REPO`
(`tools/smiteupdate.py`) y en `UPDATE_REPO` (`dist/tray.ahk`). Nunca los apuntes a un repo que
no controles: el updater descarga y ejecuta el instalador del último release.

## Traer arreglos del original

```
git fetch upstream
git log upstream/main --oneline
git cherry-pick <hash>
```

No hagas `git merge upstream/main`: reintroduciría lo que quitamos.

## Hoja de ruta

1. ~~Repo propio, updater apagado, región LAN, carpeta propia, quitar automatizaciones.~~
2. Renombrar la app (nombre, icono, ventanas, instalador).
3. Recolector de partidas match-v5 de LAN y recomendador de objetos con datos propios
   (fase 1: winrates condicionales con suavizado bayesiano).
4. Traducción al español.
5. Recomendador fase 2 (modelo) y rutas de jungla recomendadas antes de la partida.

## Créditos y licencia

Basado en [Smiteless](https://github.com/bobbyroylee/smiteless) de bobbyroylee, licencia MIT.
Este proyecto conserva esa licencia: ver [LICENSE](LICENSE).
