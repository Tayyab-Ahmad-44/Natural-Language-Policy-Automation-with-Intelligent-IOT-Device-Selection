# FYP Progress 1 Presentation

## SLIDE 1: Title Slide
**Natural Language Policy Automation with Intelligent IoT Device Selection**

FYP Progress 1 Presentation | December 10, 2025

---

## SLIDE 2: Problem & Solution

**Problem:**
- IoT devices require complex technical configuration
- Users need expertise to automate multiple devices
- No unified natural language interface

**Our Solution:**
Convert natural language into automated IoT actions using AI

---

## SLIDE 3: Project Objectives

✅ Objective 1: Device registration & management system  
✅ Objective 2: Parse natural language into executable actions  
⏳ Objective 3: Intelligent device recommendation  
⏳ Objective 4: Multi-domain testing  
⏳ Objective 5: User authentication

**Progress: 2 of 5 objectives completed**

---

## SLIDE 4: System Architecture

```
User Interface (Next.js)
    ↓ REST API
Backend (FastAPI)
    ↓ Database (SQLite)
Device Management
    ↓ LLM API (Groq)
IoT Devices
```

**Key Components:** Device API | Policy Parser | Task Breakdown | Scheduler

---

## SLIDE 5: Core Feature 1 - Device Management

**What we built:**
- Register IoT devices with capabilities
- Store device endpoints and parameters
- Manage device library

**Example Device:**
```
Living Room Light
├── Turn On
├── Turn Off
├── Dim (parameter: percentage)
└── Set Color (parameter: hex)
```

---

## SLIDE 6: Core Feature 2 - Natural Language Parsing

**User Input:**
*"At 8 PM, turn off all lights and lock the front door"*

**System Output:**
```
Time: 20:00
Actions:
- Turn off Living Room Light
- Lock Front Door
```

**Technology:** Groq LLM parses intent → execution plan

---

## SLIDE 7: Core Feature 3 - Task Management

**Complex Task → Multiple Policies**

Input: *"Morning routine at 7 AM"*

System generates:
1. Open curtains at 07:00
2. Brew coffee at 07:00
3. Set thermostat at 07:00

---

## SLIDE 8: Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI + Python |
| Database | SQLite + SQLAlchemy |
| LLM | Groq API (llama-3.3-70b) |
| Frontend | Next.js + TypeScript |
| Styling | Tailwind CSS |

**APIs:** 13 REST endpoints with full CRUD operations

---

## SLIDE 9: Multi-Domain Support

Tested across 5 domains with 40+ devices:

🏠 **Smart Home** - Lights, locks, thermostat, cameras  
🏭 **Industrial** - Machinery, conveyors, alarms, robots  
🏥 **Healthcare** - Medical beds, monitors  
🏢 **Building** - Security, access control  
🌆 **Smart City** - Traffic, utilities, surveillance

---

## SLIDE 10: Database Schema

```
Device ──→ Capability
Task ───→ Policy ───→ Execution Plan (JSON)
```

**Entities:**
- Device (name, type)
- Capability (endpoint, method, parameters)
- Policy (time window, execution plan)
- Task (groups multiple policies)

---

## SLIDE 11: What's Working

✅ Device registration and listing  
✅ Natural language to execution conversion  
✅ Policy creation with time scheduling  
✅ Task decomposition into policies  
✅ Interactive preview feature  
✅ Complete frontend dashboard  
✅ Full database integration

---

## SLIDE 12: Challenges & Solutions

| Issue | Solution |
|-------|----------|
| LLM formatting | JSON parsing + error handling |
| Device coordination | Many-to-Many relationships |
| Language ambiguity | LLM instructions + preview |
| Time consistency | Standardized HH:MM format |
| CORS errors | FastAPI middleware |

---

## SLIDE 13: Demo Workflow

**User Journey:**
1. Register device (Living Room Light)
2. Create policy (natural language input)
3. Preview execution plan
4. Save policy
5. Schedule executes automatically

---

## SLIDE 14: Project Status & Next Steps

**Current Status:**
- ✅ Full working backend & frontend
- ✅ LLM integration operational
- ✅ Database complete
- ✅ 2 objectives achieved

**Next Phase:**
- Conditional policies (if-then-else)
- Device recommendations
- User authentication
- Advanced scheduling

---

## SLIDE 15: Conclusion

**Achievement:**
Built a complete IoT automation platform where users describe what they want in natural language, and the system executes it.

**Key Impact:**
No technical expertise needed to automate IoT environments

**Applicable to:** Smart homes, factories, hospitals, buildings, cities

---
