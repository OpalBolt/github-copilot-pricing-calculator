# Router Pricing

This context compares model prices across customer-facing AI routing services. It keeps router offers separate and describes where inference runs.

## Language

**Router**:
A customer-facing service that sells access to models and selects an inference backend. Cortecs, EUrouter, and OpenRouter are routers.
_Avoid_: Source, provider

**Provider**:
A named inference backend used by a Router. The calculator shows Provider names only when the router publishes them.
_Avoid_: Router, source

**Canonical organization name**:
The display name used for an owner or Provider across all routers. Known upstream aliases map to one label, while source IDs and unknown names remain unchanged.
_Avoid_: Source name, raw organization name

**Router Model**:
A model listing published by one router. The same underlying model on two routers is two Router Models.
_Avoid_: Model offer, source model

**Router Model Offer**:
The table row for one Router Model. It shows the Router Price for the active routing mode.
_Avoid_: Offer, source-model offer

**Router Price**:
The model-level price bundle published by a router for one routing mode. It is an advertised comparison price, not a quote for a specific inference backend.
_Avoid_: Provider price, route price

**Unrestricted inference**:
Inference without an EU hosting constraint. It is the calculator's default mode and makes no claim about processing location.
_Avoid_: Global inference, standard inference

**EU routing**:
A router's documented mode for European hosting or processing. Each router makes a different claim, which the calculator identifies without treating the guarantees as identical.
_Avoid_: EU-native, sovereign, EU-hosted inference

**Input-rate cache fallback**:
An estimated cached-input rate used when a Router Price does not include one. It equals the input rate and must be visibly marked because a separate cache price might exist.
_Avoid_: Cache price, cache-read price

**Plan-restricted price**:
A Router Price that requires a specific router plan or account entitlement. Its presence does not prove that the current user can use the routing mode.
_Avoid_: Premium price

**Stale router data**:
Router data kept from the last successful fetch after a later refresh fails. The calculator marks it per router and excludes it after seven days.
_Avoid_: Current data, fresh data

**Listed availability**:
A Router Model published by its router at the recorded fetch time. It does not guarantee live capacity, account access, or request-time routing.
_Avoid_: Available now, live availability
