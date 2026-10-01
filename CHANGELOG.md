# Smiteless (adaptación LAN) — Notas de versión

## Sin publicar — base propia para LAN

Primera versión de nuestro fork, basado en Smiteless v0.9.72 de bobbyroylee (licencia MIT). El historial del proyecto original está en docs/CHANGELOG_ORIGINAL.md.

**Lo que vas a notar**
- **Región LAN por defecto.** Rank, historial, scout y estadísticas de builds salen de LAN (la1). Se cambia en Ajustes → REGION.
- **CLIMB MODE en lugar de MAX ELO.** Enciende todas las lecturas y te recuerda tu pool en champ select: tu main y tu backup van primero en GOOD THIS GAME (un clic hace hover) y si haces hover a otro campeón aparece "⚠ off your pool". Ya no acepta, banea ni lockea por ti.
- **El jungla enemigo solo aparece cuando el juego te lo mostró:** "seen BOTSIDE · kill 9s ago", "last seen TOPSIDE · 70s ago" o "DEAD — back 22s". Se acabó la alarma roja "NO SIGN" constante.
- **Silencio en partida sin teclado:** oculta los chats y silencia el audio de pings desde los ajustes del propio cliente; ya no escribe /fullmute all.
- **Instalador:** "Start with Windows" es una casilla, y es el mismo ajuste que ves en Ajustes → STARTUP.

**Quitado por las políticas de Riot**
- Auto-accept de la cola, auto-ban (y su lista de perma-bans), auto-lock del campeón y swaps automáticos de rol y de orden de pick.
- Escribir en el chat de la partida con teclado simulado.
- Login con usuario y contraseña guardados.
- Leer los nombres de aliados que el cliente oculta en champ select.
- Deducir dónde está el jungla enemigo a partir de su CS.

**Por dentro**
- Todo se guarda en %APPDATA%\Smiteless (antes dentro de ~/.claude, la carpeta de Claude Code).
- Clave de Riot: variable de entorno RIOT_API_KEY, un .env ignorado por git, o Ajustes.
- Actualizaciones automáticas apagadas hasta tener releases propios: ya no se descarga nada del repo original.
- Sin "Usage stats" ni enlaces al GitHub o al Firebase del autor original.
- El selftest suma cinco comprobaciones que fallan si alguna función prohibida regresa.
