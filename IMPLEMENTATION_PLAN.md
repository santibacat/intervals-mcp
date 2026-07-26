# Plan de implementación: entrenador de resistencia sobre Intervals.icu

> Actualización de julio de 2026: tras validar el flujo de biblioteca, el alcance incorpora operaciones controladas para aplicar un plan gestionado completo desde una fecha futura exacta y retirar después únicamente esa aplicación. Sigue prohibido exponer CRUD genérico de eventos. Las operaciones exigen vista previa, confirmación, hash vigente, IDs resueltos, detección de duplicados y aprobación adicional ante conflictos.

## 1. Objetivo

Construir un asistente de planificación de entrenamiento para un atleta avanzado y multideporte que:

1. Lea automáticamente su historial, carga y datos de bienestar desde Intervals.icu.
2. Genere planes de entrenamiento personalizados a partir de objetivos, disponibilidad y restricciones.
3. Cree entrenamientos estructurados de carrera, ciclismo y natación.
4. Cree una vista previa editable dentro de la biblioteca de planes de Intervals.icu.
5. Requiera que el usuario aplique manualmente el plan revisado al calendario.
6. Aproveche la conexión existente Intervals.icu → Garmin Connect → dispositivo Garmin.
7. Lea posteriormente la actividad completada y ajuste las siguientes propuestas.
8. Exponga contexto y operaciones de borrador mediante un servidor MCP para que una LLM pueda crear, consultar y modificar planes bajo el namespace `[IA]` sin aplicarlos directamente al calendario.

El primer objetivo no es sustituir completamente a un entrenador humano, sino demostrar un circuito fiable y seguro:

```text
Intervals.icu → planificador → propuesta → aprobación → Intervals.icu
      ↑                                                   ↓
      └──────── actividad completada ← Garmin ←───────────┘
```

## 2. Alcance inicial

### Incluido en el MVP

- Un solo atleta y una sola cuenta de Intervals.icu.
- Aplicación local ejecutada desde línea de comandos.
- Servidor MCP local construido con el SDK oficial de MCP para Python.
- Transporte `stdio` por defecto.
- Intervals.icu como interfaz para revisar la biblioteca de borradores, aplicar un plan al calendario y ver su ejecución.
- Lectura de perfil, actividades, calendario, fitness/fatiga y bienestar disponible.
- Configuración de objetivos A/B/C, disponibilidad y restricciones.
- Generación de una semana de entrenamiento.
- Entrenamientos estructurados por ritmo, frecuencia cardíaca, potencia, tiempo o distancia.
- Reglas deterministas de seguridad y coherencia.
- Uso opcional de una LLM con salida JSON validada.
- Vista previa dentro de la biblioteca de planes de Intervals.icu.
- Aplicación manual del plan al calendario desde la interfaz de Intervals.icu.
- Asociación entre entrenamiento planificado y actividad completada cuando los datos lo permitan.
- Informe semanal de cumplimiento y propuesta de adaptación.

### Fuera del MVP

- Aplicación móvil.
- Interfaz web multiusuario.
- Integración directa con la API de Garmin.
- Cobros, suscripciones o gestión de otros atletas.
- Diagnóstico médico o de lesiones.
- Automatización de nutrición.
- Publicación completamente autónoma sin revisión humana.
- Herramientas MCP con capacidad para aplicar planes al calendario, modificar eventos del calendario o eliminar contenido fuera del namespace `[IA]`.
- Dashboard propio, FastAPI y SQLite; se añadirán solo si el flujo nativo de Intervals.icu resulta insuficiente.
- Optimización avanzada para competiciones encadenadas o temporadas profesionales.

## 3. Principios de diseño

1. **Intervals.icu es la fuente de verdad operativa.** Aloja el calendario aprobado, los entrenamientos ejecutables y las actividades completadas; Garmin se usa para ejecutarlos y registrar resultados.
2. **Lectura antes que escritura.** La integración empezará en modo de solo lectura.
3. **La LLM propone; las reglas validan.** La LLM puede editar borradores de biblioteca, pero ninguna salida se aplicará directamente al calendario.
4. **Aprobación explícita en Intervals.icu.** La LLM puede escribir únicamente planes privados con prefijo `[IA]` y marcador de gestión; el humano aplica manualmente el plan elegido al calendario.
5. **Cambios acotados y reversibles.** Las herramientas MCP solo pueden modificar planes y workouts que superen ambas comprobaciones de propiedad.
6. **Planificación progresiva.** Mantendremos una visión de temporada, pero el usuario aplicará al calendario únicamente bloques revisados.
7. **Datos mínimos.** Las claves, datos personales y respuestas completas de la API no se guardarán en el repositorio.
8. **Degradación segura.** Si faltan datos, hay inconsistencias o la confianza es baja, el sistema genera una advertencia en vez de improvisar.
9. **MCP opera sobre la biblioteca, no el calendario.** Las herramientas accesibles a una LLM crean o modifican borradores remotos bajo `[IA]`, pero no pueden aplicarlos al calendario.
10. **Una sola lógica de negocio.** CLI y MCP llaman a los mismos servicios de aplicación; FastAPI podrá añadirse después sin reimplementar planificación ni permisos.

## 4. Restricciones conocidas de la integración

- Intervals.icu envía a Garmin los entrenamientos planificados de aproximadamente los próximos siete días.
- Los entrenamientos estructurados deben crearse en un formato compatible con Intervals.icu y con el deporte/dispositivo Garmin correspondiente.
- Garmin puede no devolver a Intervals.icu actividades que se originaron en otra plataforma y solo fueron copiadas a Garmin Connect. Para Zwift u otros servicios conviene conectarlos directamente con Intervals.icu.
- Los planes futuros creados dentro de Garmin no pueden utilizarse como fuente del calendario de Intervals.icu.
- La representación detallada de fuerza, ejercicios, series y repeticiones puede ser menos completa que la de carrera o ciclismo.
- Los cambios de última hora deben comprobarse tanto en Garmin Connect como en el dispositivo, especialmente en ciclocomputadores Edge.

### Capacidades de escritura que utilizaremos

La API de Intervals.icu permite cubrir el flujo final sin construir un calendario alternativo:

- Listar eventos del calendario por rango de fechas.
- Crear, actualizar y eliminar eventos individuales.
- Crear o actualizar entrenamientos en bloque mediante `events/bulk?upsert=true`.
- Identificar nuestros eventos con `external_id`, que solo se empareja con contenido creado por nuestra aplicación.
- Eliminar en bloque eventos propios.
- Crear workouts estructurados con la sintaxis nativa de Intervals.icu en `description`, o mediante archivos ZWO, FIT, MRC o ERG.
- Crear carpetas/planes en la biblioteca y cargar workouts en ellas mediante endpoints de workouts.
- Leer los workouts resultantes, incluido `workout_doc`, y descargarlos en formatos compatibles.

Para el MVP probaremos primero los endpoints de contenedores, planes y workouts de la biblioteca. La API modela `FOLDER` y `PLAN` como contenedores del mismo nivel, por lo que no asumiremos que un plan puede anidarse dentro de una carpeta. La LLM escribirá exclusivamente planes privados con prefijo `[IA]` y marcador `[intervals-mcp:managed]`; el usuario aplicará el plan al calendario desde la interfaz de Intervals.icu. No escribiremos borradores directamente en los próximos siete días del calendario porque podrían sincronizarse con Garmin antes de revisarlos.

## 5. Arquitectura propuesta

```text
┌──────────────────────────────────────────────────────────┐
│ Interfaces                                               │
│ CLI local          MCP Server          Intervals.icu UI   │
│ diagnóstico        LLM/drafts          revisión/aplicar   │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│ Servicio de aplicación                                  │
│                                                         │
│  Athlete Context ── Planner ── Safety Validator         │
│          │              │               │               │
│          │          LLM Adapter      Rule Engine         │
│          │              │               │               │
│          └──── Library Draft Service ──┘                │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│ Intervals.icu API client                                │
│ activities, wellness, [IA] plans and workouts     │
└──────────────────────────┬───────────────────────────────┘
                │
       Intervals.icu ↔ Garmin
```

### Stack recomendado

- Python 3.12 o superior.
- `uv` para entorno y dependencias.
- `httpx` para el cliente HTTP.
- `pydantic` para configuración, modelos y validación de salidas.
- `typer` para la CLI.
- FastAPI y Uvicorn quedan previstos, pero no se añadirán hasta que exista un caso de uso que la UI de Intervals.icu no cubra.
- SDK oficial de MCP para Python (`mcp[cli]`) y su API `FastMCP`.
- `stdio` para desarrollo/local; Streamable HTTP podrá añadirse junto con FastAPI si más adelante necesitamos acceso remoto.
- SQLite queda pospuesto. Si se añade, guardará solo versiones, aprobaciones y auditoría, nunca una copia autoritativa del calendario o las actividades.
- `pytest`, `respx` y fixtures anonimizados para pruebas.
- SDK de la LLM detrás de una interfaz propia para no acoplar el dominio a un proveedor.
- `ruff` y `mypy` para calidad estática.

## 6. Estructura prevista del repositorio

```text
intervals-mcp/
├── README.md
├── IMPLEMENTATION_PLAN.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── athlete.example.yaml
│   └── rules.default.yaml
├── src/intervals_mcp/
│   ├── cli.py
│   ├── config.py
│   ├── mcp/
│   │   ├── server.py
│   │   ├── resources.py
│   │   ├── tools.py
│   │   └── prompts.py
│   ├── models/
│   │   ├── athlete.py
│   │   ├── activity.py
│   │   ├── goal.py
│   │   ├── workout.py
│   │   └── proposal.py
│   ├── intervals/
│   │   ├── client.py
│   │   ├── schemas.py
│   │   └── workout_format.py
│   ├── planning/
│   │   ├── context.py
│   │   ├── periodization.py
│   │   ├── weekly_planner.py
│   │   └── workout_library.py
│   ├── validation/
│   │   ├── rules.py
│   │   └── report.py
│   ├── llm/
│   │   ├── base.py
│   │   ├── prompts.py
│   │   └── provider.py
│   ├── publishing/
│   │   ├── library_drafts.py
│   │   └── calendar_events.py
│   ├── services/
│   │   ├── athlete_service.py
│   │   ├── plan_service.py
│   │   └── validation_service.py
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── contract/
└── var/                    # caché temporal, ignorada por git
```

### Experiencia de uso sin dashboard propio

Intervals.icu será también la interfaz visual del MVP:

1. La LLM consulta mediante MCP el atleta, los objetivos, el calendario y la carga reciente.
2. Crea un plan privado de biblioteca con prefijo `[IA]` y marcador gestionado.
3. El usuario abre Intervals.icu y revisa el plan y cada entrenamiento estructurado.
4. Puede pedir cambios conversando con la LLM; las herramientas MCP actualizan únicamente ese borrador.
5. Cuando está conforme, el usuario aplica manualmente el plan al calendario desde Intervals.icu.
6. Intervals.icu lo sincroniza con Garmin dentro de su ventana operativa.
7. Las actividades completadas vuelven a Intervals.icu y alimentan la siguiente revisión.

Flujo previsto:

```text
LLM + MCP
   │ crea/modifica por API
   ▼
Intervals.icu / Library / [IA] plans
   │
   │ usuario revisa y aplica el plan
   ▼
Intervals.icu / Calendar
   │
   ▼
Garmin: ejecución → actividad completada → Intervals.icu
```

No construiremos inicialmente gráficas, histórico, calendario alternativo ni pantalla de aprobación. Si más adelante necesitamos comparación de versiones, colaboración concurrente, auditoría detallada o aprobación desde el chat, incorporaremos SQLite y un dashboard FastAPI pequeño. Esa ampliación no cambiará el cliente de Intervals ni el motor de planificación.

## 7. Configuración del atleta

La información que no pueda obtenerse de Intervals.icu se definirá en `config/athlete.yaml`:

```yaml
athlete:
  timezone: Europe/Madrid
  experience: advanced

availability:
  monday: ["06:30-08:00"]
  tuesday: ["18:00-20:00"]
  wednesday: []
  thursday: ["06:30-08:00"]
  friday: ["18:00-19:30"]
  saturday: ["08:00-13:00"]
  sunday: ["08:00-12:00"]

goals:
  - name: Evento principal
    date: 2026-10-18
    sport: triathlon
    distance: custom
    priority: A
    target: finish_strong

preferences:
  rest_days: [wednesday]
  long_run_days: [sunday]
  long_ride_days: [saturday]
  strength_sessions_per_week: 1
  preferred_intensity_basis:
    run: pace
    ride: power
    swim: pace

constraints:
  max_weekly_hours: 12
  excluded_exercises: []
  injury_notes: []
```

Las zonas, FTP, umbrales y carga se leerán de Intervals.icu cuando sea posible. Si se configuran localmente, el sistema señalará cualquier discrepancia en lugar de elegir silenciosamente un valor.

## 8. Modelo de datos mínimo

### `AthleteSnapshot`

- Fecha y zona horaria.
- Fitness, fatiga y forma disponibles.
- HRV, sueño, pulso en reposo, peso y valoración subjetiva disponibles.
- Volumen y carga de las últimas 1, 4, 6 y 12 semanas por deporte.
- Distribución de intensidad.
- Mejores esfuerzos o umbrales relevantes.
- Entrenamientos planificados y completados.
- Alertas por datos ausentes o anómalos.

### `TrainingGoal`

- Deporte, distancia y desnivel.
- Fecha y prioridad A/B/C.
- Objetivo de rendimiento.
- Experiencia previa.
- Restricciones específicas de la prueba.

### `WorkoutProposal`

- Fecha, deporte, nombre y propósito.
- Duración o distancia estimada.
- Calentamiento, bloques, recuperaciones y vuelta a la calma.
- Objetivos por zona, ritmo, pulso o potencia.
- Carga estimada.
- Importancia: clave, secundaria u opcional.
- Motivo de inclusión.
- Datos utilizados y nivel de confianza.

### `WeeklyProposal`

- Resumen del contexto.
- Objetivo de la semana.
- Lista de entrenamientos.
- Totales por deporte.
- Carga e intensidad estimadas.
- Diferencia respecto a semanas recientes.
- Advertencias del validador.
- Estado de validación local antes de escribir en la biblioteca.
- ID de carpeta, plan y workouts devueltos por Intervals.icu.
- Hash esperado del borrador remoto para detectar cambios desde otra sesión.
- Autor/origen: humano, MCP, importación o generador interno.

### Versionado ligero del MVP

- Intervals.icu conserva el ID y contenido actual del plan de biblioteca.
- Las herramientas de edición exigirán un hash del contenido leído previamente para evitar sobrescrituras silenciosas.
- Cuando se necesite conservar una versión, se clonará el plan gestionado con un sufijo de versión.
- Si este mecanismo resulta insuficiente, SQLite añadirá posteriormente versiones inmutables y auditoría sin cambiar el modelo de dominio.

## 9. Reglas de seguridad iniciales

Los valores exactos serán configurables y se calibrarán con su historial. Inicialmente se implementarán reglas conservadoras:

- Al menos un día sin sesión exigente por semana.
- Límite configurable de sesiones intensas por disciplina y semana.
- Prohibición por defecto de sesiones clave consecutivas del mismo deporte.
- Control de crecimiento de volumen y carga frente a las semanas recientes.
- Límite separado para el crecimiento del volumen de carrera.
- Límite para la proporción de la tirada larga sobre el volumen semanal de carrera.
- Recuperación tras tirada larga, salida larga, brick exigente o competición.
- Compatibilidad entre fuerza de piernas y sesiones clave cercanas.
- Semana de descarga configurable dentro de cada bloque.
- Taper dependiente del tipo y prioridad del evento.
- Rechazo si faltan zonas necesarias para construir los objetivos.
- Rechazo ante fechas, duraciones, distancias o intensidades imposibles.
- Advertencia ante HRV, sueño, pulso en reposo, dolor, enfermedad o fatiga subjetiva anómalos.
- Ninguna señal de bienestar aislada cancelará automáticamente una sesión: se combinarán tendencia, contexto y valoración del atleta.
- Síntomas de lesión o enfermedad producirán una pausa y recomendarán valoración profesional, no un nuevo diagnóstico de la LLM.

Todas las reglas producirán códigos explicables, por ejemplo `RUN_VOLUME_RAMP_HIGH` o `BACK_TO_BACK_KEY_SESSIONS`.

## 10. Uso de la LLM

### Responsabilidades permitidas

- Traducir objetivos y restricciones expresados en lenguaje natural.
- Proponer la organización de una semana dentro de límites calculados.
- Seleccionar y parametrizar sesiones de una biblioteca aprobada.
- Explicar la intención y los compromisos del plan.
- Sugerir adaptaciones cuando se incumpla una sesión.
- Generar una salida JSON ajustada a un esquema estricto.

### Responsabilidades no permitidas

- Publicar directamente.
- Inventar zonas, FTP, ritmos o lesiones.
- Ignorar los límites del motor de reglas.
- Emitir diagnósticos médicos.
- Cambiar de forma silenciosa un objetivo o una restricción.

### Flujo de generación

1. El código resume los datos en un `PlanningContext` pequeño y explícito.
2. El planificador calcula límites de volumen, carga y sesiones clave.
3. La LLM devuelve únicamente un `WeeklyProposal` estructurado.
4. Pydantic valida tipos, rangos y campos obligatorios.
5. El motor de reglas valida coherencia deportiva y seguridad.
6. Si hay errores, se rechaza o se permite una única regeneración con los errores concretos.
7. Se crea una vista previa legible.
8. El usuario aprueba, modifica o rechaza.

## 11. Servidor MCP

MCP será la interfaz de trabajo para una LLM externa —por ejemplo, un cliente de escritorio o un agente— y no un segundo planificador. El servidor expondrá capacidades del dominio y la LLM decidirá cómo combinarlas. La lógica, validación, versionado y permisos permanecerán en Python.

### Transporte y despliegue

- Desarrollo inicial: servidor MCP por `stdio`, iniciado con `uv run`, sin puerto de red y con acceso local.
- Pruebas: MCP Inspector y un cliente MCP automatizado.
- Opción posterior: Streamable HTTP en `/mcp`, montado en una aplicación FastAPI/ASGI si necesitamos acceso por red.
- Cualquier despliegue remoto requerirá autenticación, TLS, autorización por usuario y una revisión específica de amenazas antes de activarse.

### Recursos MCP de solo lectura

Los recursos ofrecerán contexto estable y direccionable sin convertir cada lectura en una acción:

```text
athlete://current/profile
athlete://current/snapshot/latest
athlete://current/zones
calendar://week/{yyyy-mm-dd}
library-plan://{plan_id}
library-plan://{plan_id}/validation
rules://active
workout-library://catalog
```

Los snapshots entregados a clientes MCP contendrán resúmenes y procedencia, no archivos FIT completos ni secretos.

### Herramientas MCP del MVP

#### Lectura y análisis

- `get_training_context(start_date, history_days)`
- `list_goals()`
- `list_ai_draft_plans()`
- `get_ai_draft_plan(plan_id)`
- `compare_planned_vs_completed(start_date, end_date)`
- `validate_plan(plan_id, expected_hash)`

#### Mutación acotada de borradores en Intervals.icu

- `create_library_plan_draft(name, objective)`
- `clone_library_plan_draft(plan_id, expected_hash, version_label)`
- `add_workout_to_library_plan(plan_id, expected_hash, workout)`
- `update_library_workout(plan_id, expected_hash, workout_id, patch)`
- `remove_library_workout(plan_id, expected_hash, workout_id, reason)`
- `replace_library_plan_draft(plan_id, expected_hash, proposal)`
- `validate_library_plan(plan_id, expected_hash)`

Todas las mutaciones se limitarán a planes con marcador gestionado; `[IA]` será solo una convención visual. `expected_hash` proporcionará control de concurrencia optimista: si otra conversación o el usuario cambió el borrador, la herramienta fallará y obligará a la LLM a releerlo. Cuando se quiera conservar una versión, la LLM clonará primero el plan.

#### Herramientas deliberadamente no expuestas inicialmente

- Aplicar un plan al calendario.
- Crear, modificar o eliminar eventos del calendario.
- Modificar o eliminar planes que no tengan el marcador gestionado.
- Cambiar credenciales, reglas duras o límites de seguridad.
- Aprobar un plan en nombre del humano.
- Ejecutar SQL, leer archivos arbitrarios o realizar peticiones HTTP genéricas.

La aprobación consistirá en que el usuario revise el plan en Intervals.icu y lo aplique manualmente al calendario desde su interfaz.

### Prompts MCP opcionales

- `draft_training_week`: guía al cliente para leer contexto, crear un borrador y validarlo.
- `revise_invalid_plan`: incorpora errores del validador sin relajar reglas.
- `review_completed_week`: compara lo realizado y propone cambios para la semana siguiente.

Los prompts serán ayudas versionadas, no una fuente de autoridad. Cualquier cliente podrá usar las herramientas sin ellos.

### Respuestas de herramientas

Todas las herramientas devolverán contenido estructurado y compacto:

- IDs y versión resultante.
- Resumen del cambio.
- Errores y advertencias con códigos estables.
- Siguiente acción permitida.
- Indicación explícita de que el cambio está solo en la biblioteca y no se ha aplicado al calendario ni enviado a Garmin.

Nunca devolverán claves, cabeceras, trazas internas completas o datos de otros atletas.

### Aprobación y frontera de confianza

```text
LLM/MCP ── crea y modifica ──> Intervals Library / [IA]
                                           │
                                  valida reglas duras
                                           │
                                  humano revisa el plan
                                           │
                            humano pulsa "Apply plan"
                                           │
                                           ▼
                                Intervals Calendar → Garmin
```

Modificar el plan de biblioteca después de aplicarlo no debe considerarse una edición automática del calendario ya publicado. Cualquier ajuste sobre eventos del calendario se tratará como una capacidad distinta y quedará fuera del MCP inicial.

## 12. Fases de implementación

### Fase 0 — Preparación y seguridad

**Objetivo:** preparar un proyecto reproducible sin realizar escrituras externas.

Tareas:

- Inicializar proyecto Python, dependencias, linting y pruebas.
- Añadir `.gitignore`, `.env.example` y carga segura de secretos.
- Documentar cómo crear una API key personal de Intervals.icu.
- Implementar configuración y logging con redacción de secretos.
- Añadir `--dry-run` como comportamiento predeterminado.
- Definir prefijo para eventos propios, por ejemplo `[INTERVALS-MCP-MVP]`.

Criterio de salida:

- El proyecto instala y ejecuta tests localmente.
- Ninguna clave aparece en logs, fixtures o Git.

### Fase 1 — Cliente de Intervals.icu en solo lectura

**Objetivo:** confirmar autenticación y conocer los datos reales disponibles.

Tareas:

- Implementar cliente HTTP con timeouts, reintentos limitados y errores tipados.
- Consultar perfil/configuración accesible.
- Descargar actividades recientes.
- Descargar calendario y entrenamientos planificados.
- Descargar bienestar y métricas de fitness/fatiga disponibles.
- Implementar paginación/rangos de fechas y caché local.
- Crear `intervals-mcp inspect` con resumen anonimizable.
- Guardar fixtures sanitizados para pruebas contractuales.

Criterio de salida:

- Podemos resumir correctamente al menos 6-12 semanas sin modificar Intervals.icu.
- Sabemos qué campos llegan realmente desde el Garmin conectado.

### Fase 2 — Prueba controlada de la biblioteca de planes

**Objetivo:** demostrar que podemos crear y modificar un borrador visible en Intervals.icu sin tocar el calendario ni Garmin.

Tareas:

- Implementar serialización de un entrenamiento sencillo soportado por Intervals.icu.
- Crear un plan de prueba privado con prefijo y marcador gestionados.
- Añadir un workout estructurado mediante la sintaxis nativa en `description`.
- Leerlo de vuelta y comprobar que Intervals.icu generó sus pasos y carga.
- Modificarlo, clonarlo y eliminar únicamente el clon de prueba.
- Verificar que ninguna operación creó eventos en el calendario.

Criterio de salida:

- El borrador se ve y se puede editar en la biblioteca de Intervals.icu.
- Ningún contenido no gestionado, evento de calendario o dato de Garmin resulta modificado.

### Fase 3 — Cierre del circuito con actividad completada

**Objetivo:** aplicar manualmente un plan revisado y comprobar el circuito Intervals.icu → Garmin → Intervals.icu.

Tareas:

- Aplicar manualmente desde Intervals.icu el plan de prueba al calendario.
- Confirmar su aparición en Garmin Connect y el dispositivo.
- Ejecutar o simular de forma segura el entrenamiento de prueba.
- Esperar la sincronización normal de Garmin.
- Leer la actividad completada desde Intervals.icu.
- Relacionarla con el evento planificado mediante IDs disponibles o heurísticas controladas de fecha, deporte y duración.
- Calcular cumplimiento de duración, distancia, pasos y objetivos.
- Registrar diferencias entre prescrito y ejecutado.

Criterio de salida:

- El sistema detecta la actividad y genera un informe de cumplimiento reproducible.

### Fase 4 — Contexto y motor determinista

**Objetivo:** poder construir y validar planes sin depender de una LLM.

Tareas:

- Implementar modelos de atleta, objetivos, disponibilidad y restricciones.
- Calcular resúmenes por deporte y ventana temporal.
- Implementar carga, volumen, frecuencia e intensidad disponibles.
- Crear una pequeña biblioteca versionada de sesiones.
- Implementar reglas de seguridad y reporte de errores/advertencias.
- Construir manualmente una semana usando la biblioteca.
- Validarla y producir vista previa.

Criterio de salida:

- El sistema rechaza fixtures deliberadamente peligrosos o incoherentes.
- Una semana manual válida puede cargarse como plan gestionado `[IA]`.

### Fase 5 — Servidor MCP y edición de borradores remotos

**Objetivo:** permitir que una LLM consulte el contexto y trabaje de forma segura sobre planes gestionados `[IA]` en Intervals.icu.

Tareas:

- Añadir el SDK oficial `mcp[cli]` con `uv`.
- Implementar servidor FastMCP por `stdio`.
- Exponer los recursos de atleta, calendario, reglas, biblioteca y borradores.
- Exponer herramientas de lectura, creación, clonación, edición y validación de planes de biblioteca.
- Restringir todas las mutaciones a planes comprobados por marcador e ID de pertenencia.
- Implementar concurrencia optimista mediante el hash esperado del plan remoto.
- Probar el contrato con MCP Inspector y un cliente automatizado.
- Confirmar que ninguna herramienta MCP puede crear o cambiar eventos del calendario.

Criterio de salida:

- Una LLM puede leer contexto, crear un plan, modificar una sesión y validarlo.
- Las ediciones concurrentes producen un conflicto explícito y no una sobrescritura silenciosa.
- El resultado aparece como plan `[IA]`, pero no en el calendario ni en Garmin.
- El usuario puede revisarlo y aplicarlo usando únicamente Intervals.icu.

### Fase 6 — Generación asistida por LLM

**Objetivo:** generar propuestas útiles y estructuradas sin ceder el control.

Tareas:

- Crear interfaz de proveedor y un proveedor inicial.
- Definir prompt versionado y esquema JSON estricto.
- Enviar solo un resumen necesario del atleta.
- Validar respuesta con Pydantic.
- Ejecutar reglas deterministas después de cada respuesta.
- Implementar una regeneración guiada por errores.
- Guardar modelo, versión de prompt, parámetros y hash del contexto.
- Mantener modo sin LLM para pruebas.

Criterio de salida:

- La misma fixture produce propuestas válidas o fallos explicables.
- Las propuestas inválidas se marcan claramente y no se presentan como listas para aplicar al calendario.

### Fase 7 — Ciclo semanal adaptativo

**Objetivo:** pasar de generar sesiones aisladas a gestionar semanas sucesivas.

Tareas:

- Generar una propuesta semanal a partir de historial, objetivo y disponibilidad.
- Publicar solo sesiones aprobadas dentro de la ventana operativa.
- Detectar sesiones omitidas, modificadas o realizadas fuera del plan.
- Preguntar por RPE, dolor, enfermedad y cambios de disponibilidad.
- Crear un informe semanal.
- Proponer ajustes para la semana siguiente.
- Evitar replanificar retrospectivamente o cambiar una sesión ya iniciada.

Criterio de salida:

- Dos semanas consecutivas pueden planificarse, ejecutarse y revisarse sin inconsistencias.

### Fase 8 — Evaluación frente a Athletica y endurecimiento

**Objetivo:** decidir si el sistema propio aporta suficiente valor.

Tareas:

- Comparar durante 2-4 semanas, sin ejecutar planes contradictorios:
  - volumen por deporte;
  - intensidad;
  - sesiones clave;
  - descanso;
  - adaptación ante sesiones omitidas;
  - claridad de las explicaciones.
- Revisar las propuestas con el atleta y, si es posible, con su entrenador actual.
- Ajustar reglas y biblioteca.
- Añadir copias de seguridad, migraciones y recuperación ante errores.
- Decidir si merece la pena añadir interfaz web, varios atletas o integración directa con otros servicios.

Criterio de salida:

- Decisión documentada: continuar, mantener como herramienta auxiliar o usar Athletica.

## 13. Comandos previstos

```bash
# Comprueba configuración y autenticación sin escribir
intervals-mcp doctor

# Lee y resume datos recientes
intervals-mcp sync --days 84
intervals-mcp inspect

# Genera y valida una propuesta sin escribir
intervals-mcp propose --week 2026-07-20

# Lista los borradores controlados en Intervals.icu
intervals-mcp drafts list

# Muestra qué se escribiría en un plan [IA]
intervals-mcp drafts push proposal.json --dry-run

# Crea o actualiza un plan de biblioteca tras confirmación
intervals-mcp drafts push proposal.json

# Revisa cumplimiento y genera informe
intervals-mcp review --week 2026-07-20

# Inicia el servidor MCP local por stdio
intervals-mcp mcp serve --transport stdio

```

No habrá inicialmente un comando para aplicar planes al calendario: esa aprobación se hará manualmente en Intervals.icu.

## 14. Estrategia de pruebas

### Unitarias

- Conversión de zonas y unidades.
- Cálculo de duración y carga estimada.
- Parser/serializador de entrenamientos.
- Reglas de seguridad.
- Esquemas de salida de la LLM.
- Asociación entre plan y actividad.

### Integración local

- Cliente HTTP contra respuestas simuladas.
- Generación → validación → serialización → cliente de biblioteca simulado.
- Recursos, herramientas y respuestas estructuradas del servidor MCP.
- Conflictos de hash y aislamiento del namespace gestionado.

### Contrato MCP

- Descubrimiento de herramientas, recursos y prompts con MCP Inspector.
- Validación de schemas de entrada y salida.
- Confirmación de que las herramientas solo escriben planes gestionados y nunca en el calendario.
- Pruebas de repetición, timeouts, cancelación y llamadas concurrentes.
- Pruebas negativas para acceso a secretos, rutas arbitrarias y operaciones no autorizadas.

### Contractuales con Intervals.icu

- Lectura de endpoints reales en modo de solo lectura.
- Comparación de schemas con fixtures anonimizados.
- Pruebas manuales y excluidas de CI para crear, leer, modificar y clonar un plan gestionado.

### Extremo a extremo manual

- Crear un plan identificable `[IA]` y revisarlo en Intervals.icu.
- Aplicarlo manualmente al calendario.
- Confirmarla en Garmin Connect y en el dispositivo.
- Completarla o registrar una actividad controlada.
- Confirmar retorno y asociación.
- Retirar los artefactos de prueba que sigan pendientes.

## 15. Seguridad, privacidad y operaciones

- La API key vivirá en `.env` o en el almacén de credenciales del sistema, nunca en Git.
- Los logs no incluirán cabeceras de autenticación ni archivos FIT completos.
- Los datos enviados a la LLM se reducirán al mínimo y se documentarán.
- Se permitirá desactivar el envío de sueño, HRV, peso u otros datos sensibles.
- Cada escritura remota incluirá en logs un identificador de operación sin contenido sensible.
- Los reintentos de escritura comprobarán primero IDs y contenido remoto para evitar duplicados.
- La aplicación comprobará marcador y pertenencia del workout antes de editar contenido.
- Si Intervals.icu, Garmin o la LLM no están disponibles, no se publicará una alternativa improvisada.
- El transporte MCP por defecto será `stdio`; el transporte HTTP escuchará solo en localhost salvo configuración segura explícita.
- El MCP no expondrá herramientas genéricas de filesystem, shell, HTTP o SQL.
- Las herramientas mutantes aceptarán `expected_hash` y se negarán a sobrescribir un borrador cambiado.
- Los borradores creados por MCP no podrán aplicarse al calendario desde el mismo conjunto de capacidades.
- Si se habilita acceso remoto, se añadirá autenticación con tokens de corta duración, autorización por scopes, TLS y límites de tasa.

## 16. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Plan deportivamente incorrecto | Biblioteca aprobada, reglas deterministas, aprobación humana y comparación con historial |
| LLM inventa valores | Contexto estructurado, JSON schema, rechazo de valores sin procedencia |
| Duplicados en la biblioteca | Consulta previa, IDs remotos, namespace controlado y hashes |
| Cambio incorrecto en contenido existente | Solo modificar planes con marcador y workouts pertenecientes a ellos |
| Datos incompletos desde Garmin | Diagnóstico de fuentes y conexión directa de Zwift/otros servicios |
| Zonas distintas entre plataformas | Informe de discrepancias y configuración explícita por deporte |
| Demasiados datos personales enviados a la LLM | Resumen mínimo, exclusiones configurables y logs redactados |
| El atleta confía demasiado en automatización | Advertencias, aprobación obligatoria y escalado ante dolor/enfermedad |
| API cambia | Cliente aislado, pruebas contractuales y schemas tolerantes pero validados |
| Prompt injection intenta publicar o leer secretos | El MCP no ofrece esas capacidades; herramientas cerradas, schemas estrictos y permisos por servicio |
| Dos LLM editan el mismo plan | `expected_hash` obligatorio y clonación cuando se quiera conservar versión |
| Una herramienta MCP se repite por un reintento | Consulta previa e identificadores remotos estables |
| MCP HTTP queda expuesto accidentalmente | `stdio`/localhost por defecto y arranque remoto bloqueado sin configuración de seguridad |

## 17. Métricas de éxito del MVP

- 100 % de aplicaciones al calendario las realiza el usuario desde Intervals.icu.
- 0 modificaciones o eliminaciones de contenido no gestionado.
- 0 secretos registrados en repositorio o logs.
- El entrenamiento de prueba aparece correctamente en Garmin.
- La actividad completada vuelve a Intervals.icu y puede analizarse.
- Al menos dos semanas consecutivas se generan sin violar reglas duras.
- El atleta considera útiles al menos el 80 % de las sesiones propuestas, aunque las edite.
- El tiempo de revisión de una semana es inferior a diez minutos.
- Cada decisión y advertencia puede explicarse sin consultar la conversación completa de la LLM.
- Una LLM puede completar crear → editar → validar → staging usando exclusivamente MCP.
- 0 escrituras al calendario originadas directamente desde una herramienta MCP.
- 100 % de las mutaciones MCP comprueban plan gestionado, pertenencia del workout y `expected_hash`.

## 18. Primer hito que implementaremos

El primer hito abarcará únicamente las fases 0-3:

1. Crear el proyecto y la configuración segura.
2. Autenticarse contra Intervals.icu.
3. Leer y resumir las últimas actividades.
4. Crear un plan de prueba `[IA]` en la biblioteca.
5. Editar y revisar el plan dentro de Intervals.icu.
6. Aplicarlo manualmente al calendario.
7. Confirmar su llegada a Garmin.
8. Leer después la actividad completada.

Solo cuando este circuito esté probado empezaremos a construir periodización y generación con LLM. Esto separa los problemas de integración de los problemas de planificación y nos da una base verificable desde el principio.

El servidor MCP se implementará después del circuito básico de biblioteca y calendario. Así, sus herramientas envolverán servicios ya probados en vez de introducir simultáneamente problemas de protocolo, dominio e integración externa.

## 19. Información necesaria para empezar la implementación

Antes de ejecutar la Fase 1 necesitaremos:

- API key personal de Intervals.icu, guardada localmente y no compartida en el chat ni añadida al repositorio.
- ID del atleta, si el endpoint no permite usar el alias del usuario autenticado.
- Modelo de reloj Garmin y, si aplica, modelo de Edge.
- Deportes que deben sincronizarse.
- Confirmación de si las actividades de bici indoor vienen del Garmin, Zwift u otra plataforma.
- Rango histórico inicial que se desea importar; se recomienda comenzar con 12 semanas.

Para la Fase 4 necesitaremos además disponibilidad, objetivos, zonas, volumen reciente, preferencias y restricciones. Se recopilarán mediante un formulario/configuración explícito, no se inferirán silenciosamente.
