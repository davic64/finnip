# Spec Delta

## Purpose

Permitir que el usuario le pida a Finnip que tome en cuenta un dispositivo nuevo de Home Assistant, o que deje de controlar uno, sin entrar a Home Assistant y sin darle a Finnip acceso a tipos de dispositivo peligrosos.

## ADDED Requirements

### Requirement: Descubrir dispositivos nuevos
Home Bridge SHALL listar como candidatos las entidades de Home Assistant que no tienen la etiqueta `finnip` y cuyo dominio está permitido (luces, enchufes o interruptores, persianas, clima y bocinas), con su id, nombre, tipo y estado. Entidades de cualquier otro dominio, como cerraduras, alarmas o cámaras, MUST NOT aparecer como candidatos.

#### Scenario: Lámpara recién instalada
- **WHEN** el usuario dice "agregué una lámpara nueva, tómala en cuenta"
- **THEN** Finnip consulta los candidatos y menciona la lámpara nueva por su nombre en Home Assistant

#### Scenario: Una cerradura sin etiqueta
- **WHEN** Home Assistant tiene una cerradura sin la etiqueta `finnip`
- **THEN** la cerradura no aparece entre los candidatos

### Requirement: Exponer un dispositivo con confirmación
Finnip SHALL pedir confirmación al usuario, nombrando el dispositivo, antes de exponerlo. Home Bridge SHALL ponerle la etiqueta `finnip` solo si es un candidato válido, y desde ese momento el dispositivo MUST aparecer en la lista de dispositivos de Finnip y poder controlarse. Exponer una entidad fuera de los dominios permitidos MUST rechazarse sin tocar Home Assistant.

#### Scenario: Confirmar y usar
- **WHEN** Finnip pregunta "¿Agrego 'Lámpara del buró'?" y el usuario responde que sí
- **THEN** la lámpara queda etiquetada `finnip` y "prende la lámpara del buró" funciona

#### Scenario: Intento fuera de la lista permitida
- **WHEN** llega una petición para exponer `lock.puerta_principal`
- **THEN** Home Bridge la rechaza y Home Assistant no cambia

### Requirement: Dejar de controlar un dispositivo
Finnip SHALL poder quitar la etiqueta `finnip` de un dispositivo expuesto cuando el usuario lo pide. Desde ese momento el dispositivo MUST dejar de aparecer y de poder controlarse. Si algún modo lo usa, Finnip MUST avisarlo.

#### Scenario: Ocultar el ventilador
- **WHEN** el usuario dice "ya no controles el ventilador"
- **THEN** el ventilador deja de estar en la lista de Finnip, y si el Modo estudio lo usaba, Finnip avisa que ese modo lo menciona
