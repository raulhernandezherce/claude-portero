---
name: enrutador
description: Decide qué modelo o agente debe hacer cada tarea (o cada parte de una tarea) para ahorrar tokens sin perder calidad. Úsala con /enrutador, cuando el usuario pida "enruta", "reparte", "qué modelo uso", o ante tareas largas con partes mecánicas y partes difíciles. Complementa al hook portero: el portero clasifica el mensaje entero; el enrutador reparte las subtareas.
---

# Enrutador

Reparte el trabajo entre tres niveles. El objetivo es gastar el modelo caro solo donde aporta.

| Nivel | Quién lo hace | Cuándo |
|---|---|---|
| **LIGERO** | agente `rapido` (Haiku) | Buscar, listar, leer, contar, renombrar, formatear, resumir, traducir, ejecutar tests, `git status/log`. Resultado verificable sin razonar. |
| **MEDIO** | tú mismo (modelo principal) | Editar código con contexto conocido, cambios acotados, explicar, escribir textos normales, todo lo que dependa de la conversación actual. |
| **DIFÍCIL** | agente `experto` (Opus) | Arquitectura, depuración sin causa clara, concurrencia, seguridad, migraciones, rendimiento, diseño de algoritmos, decisiones con muchas alternativas. |

## Cómo enrutar

1. **Si el hook portero ya etiquetó el mensaje** (`[PORTERO: tarea LIGERA/DIFÍCIL]`), respeta esa etiqueta para la tarea completa y usa esta skill solo para repartir subtareas.
2. **Divide la tarea** en pasos. Para cada paso decide el nivel con estas reglas, en orden:
   - Si necesita lo que ya sabes de esta conversación → **MEDIO** (un subagente empezaría de cero y saldría más caro).
   - Si son una o dos llamadas a herramientas → **MEDIO**: hazlo tú, delegar cuesta más que hacerlo.
   - Si es mecánico pero voluminoso (muchos archivos, mucha salida) → **LIGERO**.
   - Si un error sería caro o hay que pensar alternativas → **DIFÍCIL**.
   - En caso de duda → **MEDIO**.
3. **Delegación**: al delegar en `rapido` o `experto`, pasa un encargo autocontenido: qué hacer, rutas o archivos concretos, y qué forma debe tener la respuesta. Lanza en paralelo los pasos independientes.
4. **Escalado**: si `rapido` responde que la tarea es más compleja de lo esperado, sube un nivel (tú o `experto`). No repitas el mismo encargo al mismo agente.
5. **Verifica** lo que devuelva un subagente antes de darlo por bueno.

## Forzar un nivel

El usuario puede empezar el mensaje con `!haiku`, `!sonnet` o `!opus` (lo gestiona el portero), o decir "hazlo tú", "usa el experto", etc. Su indicación manda sobre estas reglas.

## Qué decir al usuario

No anuncies el enrutado salvo que lo pida. Si lo pide (`/enrutador` sin tarea, o "¿cómo lo repartirías?"), muestra una tabla breve: paso → nivel → motivo en pocas palabras.
