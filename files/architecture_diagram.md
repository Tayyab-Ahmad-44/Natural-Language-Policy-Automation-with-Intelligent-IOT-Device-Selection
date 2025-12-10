# Architecture Diagram (Mermaid)

Below is the Mermaid diagram showing the system architecture. It includes the next step: a Scheduler / Executor that will execute saved policies and tasks by calling IoT device endpoints.

```mermaid
flowchart LR
  %% Users and Frontend
  U[User] -->|Interacts via UI| FE[Frontend<br/>(Next.js)]
  FE -->|REST calls| API[Backend API<br/>(FastAPI)]

  subgraph BackendServices [Backend Services]
    direction TB
    API_Device[Device API<br/>(/api/devices/*)]
    API_Policy[Policy API<br/>(/api/policies/*, /api/policies/preview)]
    API_Task[Task API<br/>(/api/tasks/*)]
    Scheduler[Scheduler / Cron trigger<br/>(/api/cron/tick)]
  end

  %% LLM and DB
  API_Policy -->|calls| LLM_Parse[LLM (Groq)\nparse_policy_with_llm]
  API_Task -->|calls| LLM_Breakdown[LLM (Groq)\nbreak_down_task]
  API_Device -->|reads/writes| DB[(SQLite / SQLAlchemy)]
  API_Policy -->|reads/writes| DB
  API_Task -->|reads/writes| DB
  Scheduler -->|queries active policies| DB

  %% Execution path
  Scheduler -->|triggers| Executor[Executor Service\n(evaluates execution_plan)]
  Executor -->|HTTP requests| Devices[IoT Devices\n(REST endpoints)]

  %% Preview flow
  FE -->|Preview request| API_Policy
  API_Policy -->|preview -> LLM| LLM_Parse
  LLM_Parse -->|returns execution plan| API_Policy
  API_Policy -->|returns preview| FE

  %% Task decomposition flow
  FE -->|Create Task| API_Task
  API_Task -->|ask LLM to decompose| LLM_Breakdown
  LLM_Breakdown -->|returns rules| API_Task
  API_Task -->|creates multiple policies| DB

  %% Notes
  subgraph Notes
    direction LR
    Note1[("Execution: Scheduler reads policies\nfrom DB and Executor sends requests to devices when\ncurrent time within policy time_window")]:::note
  end
  Scheduler --- Note1

  classDef note fill:#fff8c6,stroke:#f2c037,stroke-width:1px,color:#333;
```


You can copy the fenced Mermaid block above into any Markdown editor or into Microsoft Gamma to render the diagram. If you want a horizontal layout, different colors, or additional components (e.g., Auth service, message queue), tell me and I will update it.
