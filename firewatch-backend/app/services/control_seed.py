"""Idempotent seed for control frameworks + their controls.

Loads vendored framework files via the importer (upsert), so it is safe to call
every startup and never duplicates. Called at startup (lifespan) and runnable:
  python -m app.services.control_seed
"""

import logging

from sqlalchemy.orm import Session

from app.models.control import ControlFamily, ControlFramework, DeletedFrameworkSeed
from app.services.control_import import (
    DATA_DIR,
    VENDORED_FRAMEWORKS,
    detect_and_parse,
    import_framework,
)

logger = logging.getLogger(__name__)

# Authored category descriptions, keyed by framework name. Each entry is the EXACT
# Control.family string the importer assigns, with (display_label, description).
# sort_order is the list index. CSF names are "<Function>: <Category>"; 800-53 names
# are the family titles. These are matched by string against Control.family.
CSF_FAMILY_SEED: list[tuple[str, str, str]] = [
    ("Govern: Organizational Context", "Govern (GV)",
     "The circumstances - mission, stakeholder expectations, dependencies, and legal, "
     "regulatory, and contractual requirements - surrounding the organization's cybersecurity "
     "risk management decisions are understood."),
    ("Govern: Risk Management Strategy", "Govern (GV)",
     "The organization's priorities, constraints, risk tolerance and appetite statements, and "
     "assumptions are established, communicated, and used to support operational risk decisions."),
    ("Govern: Roles Responsibilities and Authorities", "Govern (GV)",
     "Cybersecurity roles, responsibilities, and authorities to foster accountability, "
     "performance assessment, and continuous improvement are established and communicated."),
    ("Govern: Policy", "Govern (GV)",
     "Organizational cybersecurity policy is established, communicated, and enforced."),
    ("Govern: Oversight", "Govern (GV)",
     "Results of organization-wide cybersecurity risk management activities and performance are "
     "used to inform, improve, and adjust the risk management strategy."),
    ("Govern: Cybersecurity Supply Chain Risk Management", "Govern (GV)",
     "Cyber supply chain risk management processes are identified, established, managed, "
     "monitored, and improved by organizational stakeholders."),
    ("Identify: Asset Management", "Identify (ID)",
     "Assets - data, hardware, software, systems, facilities, services, people - that enable the "
     "organization to achieve business purposes are identified and managed consistent with their "
     "relative importance to objectives and the organization's risk strategy."),
    ("Identify: Risk Assessment", "Identify (ID)",
     "The cybersecurity risk to the organization, assets, and individuals is understood by the "
     "organization."),
    ("Identify: Improvement", "Identify (ID)",
     "Improvements to organizational cybersecurity risk management processes, procedures, and "
     "activities are identified across all CSF Functions."),
    ("Protect: Identity Management Authentication and Access Control", "Protect (PR)",
     "Access to physical and logical assets is limited to authorized users, services, and "
     "hardware, and is managed commensurate with the assessed risk of unauthorized access."),
    ("Protect: Awareness and Training", "Protect (PR)",
     "The organization's personnel are provided with cybersecurity awareness and training so they "
     "can perform their cybersecurity-related tasks."),
    ("Protect: Data Security", "Protect (PR)",
     "Data are managed consistent with the organization's risk strategy to protect the "
     "confidentiality, integrity, and availability of information."),
    ("Protect: Platform Security", "Protect (PR)",
     "The hardware, software, and services of physical and virtual platforms are managed "
     "consistent with the organization's risk strategy to protect their confidentiality, "
     "integrity, and availability."),
    ("Protect: Technology Infrastructure Resilience", "Protect (PR)",
     "Security architectures are managed with the organization's risk strategy to protect asset "
     "confidentiality, integrity, and availability, and organizational resilience."),
    ("Detect: Continuous Monitoring", "Detect (DE)",
     "Assets are monitored to find anomalies, indicators of compromise, and other potentially "
     "adverse events."),
    ("Detect: Adverse Event Analysis", "Detect (DE)",
     "Anomalies, indicators of compromise, and other potentially adverse events are analyzed to "
     "characterize the events and detect cybersecurity incidents."),
    ("Respond: Incident Management", "Respond (RS)",
     "Responses to detected cybersecurity incidents are managed."),
    ("Respond: Incident Analysis", "Respond (RS)",
     "Investigations are conducted to ensure effective response and support forensics and "
     "recovery activities."),
    ("Respond: Incident Response Reporting and Communication", "Respond (RS)",
     "Response activities are coordinated with internal and external stakeholders as required by "
     "laws, regulations, or policies."),
    ("Respond: Incident Mitigation", "Respond (RS)",
     "Activities are performed to prevent expansion of an event and mitigate its effects."),
    ("Recover: Incident Recovery Plan Execution", "Recover (RC)",
     "Restoration activities are performed to ensure operational availability of systems and "
     "services affected by cybersecurity incidents."),
    ("Recover: Incident Recovery Communication", "Recover (RC)",
     "Restoration activities are coordinated with internal and external parties."),
]

NIST_800_53_FAMILY_SEED: list[tuple[str, str, str]] = [
    ("Access Control", "Access Control (AC)",
     "Controls that limit information system access to authorized users, processes, and devices, "
     "and to the types of transactions and functions that authorized users are permitted."),
    ("Awareness and Training", "Awareness and Training (AT)",
     "Controls ensuring personnel are made aware of security and privacy risks and are adequately "
     "trained to carry out their assigned responsibilities."),
    ("Audit and Accountability", "Audit and Accountability (AU)",
     "Controls for creating, protecting, and retaining audit records, and ensuring actions can be "
     "traced to individual users to support accountability."),
    ("Assessment Authorization and Monitoring", "Assessment, Authorization, and Monitoring (CA)",
     "Controls for assessing security and privacy controls, authorizing system operation, and "
     "continuously monitoring controls for ongoing effectiveness."),
    ("Configuration Management", "Configuration Management (CM)",
     "Controls for establishing and maintaining baseline configurations and inventories, and for "
     "enforcing security configuration settings throughout the system life cycle."),
    ("Contingency Planning", "Contingency Planning (CP)",
     "Controls for establishing, maintaining, and effectively implementing plans for emergency "
     "response, backup operations, and post-disaster recovery."),
    ("Identification and Authentication", "Identification and Authentication (IA)",
     "Controls for identifying and authenticating users, processes, and devices before granting "
     "access to organizational systems."),
    ("Incident Response", "Incident Response (IR)",
     "Controls for establishing an operational incident-handling capability, including "
     "preparation, detection, analysis, containment, recovery, and reporting."),
    ("Maintenance", "Maintenance (MA)",
     "Controls for performing periodic and timely maintenance on systems and for providing "
     "effective controls on the tools, techniques, and personnel used to conduct maintenance."),
    ("Media Protection", "Media Protection (MP)",
     "Controls for protecting system media, limiting access to information on media, and "
     "sanitizing or destroying media before disposal or reuse."),
    ("Personally Identifiable Information Processing and Transparency",
     "PII Processing and Transparency (PT)",
     "Controls addressing the processing of personally identifiable information and providing "
     "transparency to individuals about how their information is handled."),
    ("Personnel Security", "Personnel Security (PS)",
     "Controls ensuring individuals occupying positions of responsibility are trustworthy, and "
     "that information and systems are protected during personnel actions such as transfers and "
     "terminations."),
    ("Physical and Environmental Protection", "Physical and Environmental Protection (PE)",
     "Controls for limiting physical access to systems and facilities, and protecting them "
     "against environmental hazards and supporting infrastructure failures."),
    ("Planning", "Planning (PL)",
     "Controls for developing, documenting, and updating system security and privacy plans that "
     "describe the controls in place or planned."),
    ("Program Management", "Program Management (PM)",
     "Organization-wide controls for managing the information security and privacy programs, "
     "independent of any individual system."),
    ("Risk Assessment", "Risk Assessment (RA)",
     "Controls for assessing the risk to operations, assets, and individuals resulting from the "
     "operation of systems and the processing of information."),
    ("Supply Chain Risk Management", "Supply Chain Risk Management (SR)",
     "Controls for managing cybersecurity risks across the supply chain, including the products, "
     "services, and suppliers an organization depends on."),
    ("System and Communications Protection", "System and Communications Protection (SC)",
     "Controls for monitoring, controlling, and protecting communications at system boundaries "
     "and for employing architectural and engineering safeguards."),
    ("System and Information Integrity", "System and Information Integrity (SI)",
     "Controls for identifying, reporting, and correcting information and system flaws in a timely "
     "manner and for protecting against malicious code."),
    ("System and Services Acquisition", "System and Services Acquisition (SA)",
     "Controls for allocating resources to protect systems and for managing security and privacy "
     "throughout the system development life cycle and in acquired services."),
]

# (framework_name, seed_list) — framework_name must match the seeded ControlFramework.name.
FAMILY_SEEDS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("NIST CSF 2.0", CSF_FAMILY_SEED),
    ("NIST 800-53 Rev 5", NIST_800_53_FAMILY_SEED),
]


def seed_control_families(db: Session) -> None:
    """Upsert authored category (family) descriptions for the built-in frameworks."""
    tombstoned = {row.name for row in db.query(DeletedFrameworkSeed).all()}
    created = 0
    updated = 0
    for framework_name, families in FAMILY_SEEDS:
        if framework_name in tombstoned:
            logger.info("Skipping families for tombstoned framework: %s", framework_name)
            continue
        framework = (
            db.query(ControlFramework).filter(ControlFramework.name == framework_name).first()
        )
        if framework is None:
            logger.info("Framework not present, skipping family seed: %s", framework_name)
            continue
        existing = {
            f.name: f
            for f in db.query(ControlFamily).filter(ControlFamily.framework_id == framework.id).all()
        }
        for sort_order, (name, display_label, description) in enumerate(families):
            current = existing.get(name)
            if current is None:
                db.add(ControlFamily(
                    framework_id=framework.id,
                    name=name,
                    display_label=display_label,
                    description=description,
                    sort_order=sort_order,
                ))
                created += 1
            else:
                changed = False
                if current.display_label != display_label:
                    current.display_label = display_label
                    changed = True
                if current.description != description:
                    current.description = description
                    changed = True
                if current.sort_order != sort_order:
                    current.sort_order = sort_order
                    changed = True
                if changed:
                    updated += 1
    db.commit()
    logger.info("Seeded control families: %d created, %d updated", created, updated)


def seed_control_frameworks(db: Session) -> None:
    """Upsert the vendored frameworks/controls from app/data/frameworks."""
    total_created = 0
    total_updated = 0
    tombstoned = {row.name for row in db.query(DeletedFrameworkSeed).all()}
    for filename, name, version, description in VENDORED_FRAMEWORKS:
        if name in tombstoned:
            logger.info("Skipping tombstoned framework: %s", name)
            continue
        path = DATA_DIR / filename
        if not path.exists():
            logger.warning("Vendored framework file missing: %s", path)
            continue
        parsed = detect_and_parse(path.read_text(encoding="utf-8-sig"))
        result = import_framework(
            db,
            parsed,
            framework_name=name,
            version=version,
            description=description,
        )
        total_created += result["created"]
        total_updated += result["updated"]
    db.commit()
    logger.info(
        "Seeded control frameworks: %d created, %d updated", total_created, total_updated
    )
    seed_control_families(db)


if __name__ == "__main__":
    from app.models.database import SessionLocal

    session = SessionLocal()
    try:
        seed_control_frameworks(session)
        print("Control framework seed complete.")
    finally:
        session.close()
