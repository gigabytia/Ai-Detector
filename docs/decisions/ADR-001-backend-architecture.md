# ADR-001. Архитектура backend

Статус: принято (Milestone 1)

Backend — FastAPI со слоями `api → application → infrastructure`, домен и контракты — в отдельном пакете `shared` (`ai_detector_core`). Backend, vision-worker и shared — участники одного uv workspace; сервисы зависят только от `shared`, не друг от друга. В `shared` нет FastAPI, SQLAlchemy, Redis, OpenCV и numpy. API без состояния в памяти, поэтому масштабируется процессами.

**Почему:** Простейшая схема, при которой домен не копируется между сервисами и не зависит от инфраструктуры.
