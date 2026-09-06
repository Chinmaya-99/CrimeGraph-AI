from data_base.database import Base

from models.fir import FIRRecord
from models.contact import ContactRecord
from models.bank import BankRecord
from models.social import SocialMediaRecord
from models.crime import PreviousCrimeRecord
from models.surveillance import SurveillanceRecord
from models.entities import ExtractedEntity
from models.llm_results import LLMReasoningResult
from models.audit import AuditLedger
from models.users import User
from models.role_permission import RolePermission

print(Base.metadata.tables.keys())


from data_base.database import check_db_connection


if check_db_connection():
    print("✅ PostgreSQL connection is working")
else:
    print("❌ PostgreSQL connection failed")
