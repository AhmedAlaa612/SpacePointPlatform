import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import MegaEvent, WebsiteEvent


def slugify_event(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return s or "event"


async def unique_mega_event_slug(db: AsyncSession, base_text: str, exclude_id: UUID | None = None) -> str:
    base = slugify_event(base_text)
    slug = base
    idx = 2
    while True:
        stmt = select(MegaEvent.id).where(MegaEvent.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(MegaEvent.id != exclude_id)
        if (await db.execute(stmt)).first() is None:
            return slug
        slug = f"{base}-{idx}"
        idx += 1


async def unique_website_event_slug(db: AsyncSession, base_text: str, exclude_id: UUID | None = None) -> str:
    base = slugify_event(base_text)
    slug = base
    idx = 2
    while True:
        stmt = select(WebsiteEvent.id).where(WebsiteEvent.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(WebsiteEvent.id != exclude_id)
        if (await db.execute(stmt)).first() is None:
            return slug
        slug = f"{base}-{idx}"
        idx += 1


async def resolve_user_organization(db: AsyncSession, user: User) -> Organization | None:
    if getattr(user, "organization_id", None):
        org = await db.get(Organization, user.organization_id)
        if org is not None:
            return org
    org = (
        await db.execute(
            select(Organization).where(Organization.owner_user_id == user.id)
        )
    ).scalars().first()
    if org is not None:
        return org
    if user.contact_id:
        contact = await db.get(Contact, user.contact_id)
        if contact and contact.organization_id:
            return await db.get(Organization, contact.organization_id)
    return None


DEFAULT_WSW_AR_CONTENT: dict = {
    "enabled": True,
    "en_enabled": True,
    "title": "أسبوع الفضاء العالمي في الإمارات ٢٠٢٦",
    "subtitle": "أسبوع واحد. منظومة واحدة. آفاق لا حدود لها.",
    "tagline": "اكتشف. شارك. تواصل. قِس الأثر.",
    "date_label": "أكتوبر ٢٠٢٦ • في جميع إمارات الدولة السبع",
    "about_text": (
        "منصة عامة تجمع الفعاليات والمتحدثين والمرشدين والمتطوعين والجهات المشاركة في "
        "أسبوع الفضاء العالمي في مختلف أنحاء دولة الإمارات العربية المتحدة.\n\n"
        "اكتشف فعاليات الفضاء في دولة الإمارات، وتواصل مع المتحدثين والمرشدين، وتطوع مع الجهات المشاركة، "
        "أو بادر بتنظيم فعالية ضمن أسبوع الفضاء العالمي في مجتمعك أو مؤسستك."
    ),
    "official_note": (
        "تدعم هذه المنصة جهود التواصل والتنسيق لفعاليات أسبوع الفضاء العالمي في دولة الإمارات. "
        "نُشجع جميع الجهات المنظمة على تسجيل فعالياتها عبر الموقع الرسمي لأسبوع الفضاء العالمي."
    ),
    "primary_cta_label": "استكشف فعاليات الإمارات",
    "at_a_glance": [
        {"highlight": "٧ إمارات", "details": "تغطية شاملة على مستوى الدولة"},
        {"highlight": "الجامعات والمدارس", "details": "أنشطة طلابية ومجتمعية"},
        {"highlight": "مرشدون من القطاع", "details": "خبراء ومتخصصون في الفضاء"},
        {"highlight": "مبادرة عالمية", "details": "مرتبطة بأسبوع الفضاء العالمي"},
    ],
    "host_steps": [
        {
            "stage": "الخطوة ١",
            "title": "طوّر فكرة فعاليتك",
            "description": "خطط لورشة عمل أو محاضرة أو مسابقة أو معرض أو جلسة حوارية أو هاكاثون أو أمسية رصد فلكي لمجتمعك.",
        },
        {
            "stage": "الخطوة ٢",
            "title": "سجّل رسمياً في أسبوع الفضاء العالمي",
            "description": "سجّل نشاطك على الموقع العالمي الرسمي لأسبوع الفضاء العالمي (worldspaceweek.org).",
        },
        {
            "stage": "الخطوة ٣",
            "title": "أضف فعاليتك إلى المنصة الوطنية",
            "description": "سجّل كجهة شريكة عبر منصة سبيس بوينت وأضف صفحة فعاليتك ليتمكن المهتمون في دولة الإمارات من اكتشافها.",
        },
        {
            "stage": "الخطوة ٤",
            "title": "تواصل وتعاون",
            "description": "استقطب المتحدثين والمرشدين وسفراء الفضاء لدعم نشاطك وإثراء تجربة المشاركين.",
        },
        {
            "stage": "الخطوة ٥",
            "title": "قِس الأثر وشارك النتائج",
            "description": "ارفع مخرجات فعاليتك للمساهمة في التقرير الوطني لأثر أسبوع الفضاء العالمي في دولة الإمارات.",
        },
    ],
    "coordinator_info": {
        "name": "عبدالله السلماني",
        "role": "المنسق الوطني لأسبوع الفضاء العالمي في دولة الإمارات",
        "email": "a.alsalmani@spacepoint.ae",
        "note": "تُعد منصة أسبوع الفضاء العالمي في الإمارات مبادرة للتنسيق والتواصل المجتمعي لدعم المشاركة الفاعلة في الحملة العالمية الرسمية.",
    },
    "partners": [
        {"name": "رابطة أسبوع الفضاء العالمي", "role": "المبادرة العالمية", "logo_url": ""},
        {"name": "سبيس بوينت (SpacePoint)", "role": "منصة منظومة الفضاء في الإمارات", "logo_url": ""},
    ],
    "faqs": [
        {
            "question": "هل تُغني هذه المنصة عن التسجيل الرسمي في موقع أسبوع الفضاء العالمي؟",
            "answer": "لا، فهذه المنصة تُكمل المنصة العالمية الرسمية من خلال توفير بوابة اكتشاف وتنسيق خاصة بدولة الإمارات. نُشجع كل جهة منظمة على تسجيل فعاليتها في موقع worldspaceweek.org أولاً.",
        },
        {
            "question": "كيف يمكن لجامعتنا أو مدرستنا أو مؤسستنا إدراج فعالية؟",
            "answer": "يمكن للجهات التسجيل في بوابة سبيس بوينت (SpacePoint Portal)، وإنشاء صفحة الفعالية باستخدام النموذج الموحد، وتقديمها للنشر ضمن أسبوع الفضاء العالمي في الإمارات.",
        },
        {
            "question": "هل يحتاج الزوار إلى حساب لتصفح الفعاليات؟",
            "answer": "لا، جميع صفحات الفعاليات والجداول الزمنية وروابط التسجيل متاحة للجمهور مباشرة دون الحاجة لتسجيل الدخول.",
        },
    ],
}


DEFAULT_SATFORGE_AR_CONTENT: dict = {
    "enabled": True,
    "en_enabled": True,
    "title": "سات فورج الإمارات 2026",
    "subtitle": "التحدي الوطني للجامعات في هندسة وتصميم الأقمار الصناعية",
    "tagline": "من ابتكارات الجامعات إلى مهمات الفضاء المستقبلية",
    "city": "العين",
    "audience": "الجامعات",
    "host_org_name": "جامعة أبوظبي",
    "date_label": "11 أكتوبر – 11 نوفمبر 2026",
    "location": "جامعة أبوظبي — حرم العين",
    "about_text": (
        "يُعد تحدي «سات فورج الإمارات 2026: التحدي الوطني للجامعات في هندسة وتصميم الأقمار الصناعية» "
        "مسابقة وطنية على مستوى الجامعات تجمع الطلبة الموهوبين من مؤسسات التعليم العالي في مختلف أنحاء "
        "دولة الإمارات العربية المتحدة لتصميم وتطوير واستعراض أنظمة أقمار صناعية مبتكرة مستوحاة من الأقمار المكعبة (CubeSats).\n\n"
        "تستضيف المسابقة كلية الهندسة في جامعة أبوظبي، بدعم من وكالة الإمارات للفضاء، وأكاديمية الفضاء الوطنية، "
        "ومنصة سبيس بوينت (SpacePoint)، ومعهد البحوث للذكاء الاصطناعي والتقنيات الناشئة، والفرع الطلابي لمعهد مهندسي الكهرباء "
        "والإلكترونيات (IEEE) بجامعة أبوظبي، لتقدم تجربة تعليمية تطبيقية تجمع بين المعرفة الأكاديمية والهندسة العملية للأقمار الصناعية.\n\n"
        "ينتقل المشاركون عبر مراحل متكاملة تشمل التدريب التقني، وصياغة مفهوم المهمة، وتصميم الدوائر الإلكترونية والمحاكاة، "
        "والنمذجة ثلاثية الأبعاد، وتطوير البرمجيات، وعرض البيانات التفاعلي، وبناء النماذج الأولية للأجهزة، بإشراف نخبة من الخبراء "
        "والمتخصصين في قطاع الفضاء والتقنيات المتقدمة.\n\n"
        "سيتأهل نحو 10 فرق متميزة إلى المرحلة النهائية للمشاركة في التحضير التقني الحضوري والمعرض الوطني الختامي أمام لجنة تحكيم من خبراء القطاع."
    ),
    "benefits": [
        {
            "title": "خبرة هندسية تطبيقية",
            "description": "تطبيق المفاهيم النظرية في تصميم المهمات الفضائية والمحاكاة والإلكترونيات والبرمجة والاختبار وبناء النماذج الأولية.",
        },
        {
            "title": "إرشاد من خبراء القطاع",
            "description": "التعلم المباشر من المتخصصين العاملين في قطاع الفضاء والتقنيات المتقدمة في دولة الإمارات.",
        },
        {
            "title": "تعاون متعدد التخصصات",
            "description": "العمل ضمن فرق تجمع طلبة من مختلف التخصصات الهندسية والتقنية والعلمية.",
        },
        {
            "title": "حضور وإبراز وطني",
            "description": "استعراض الحلول المبتكرة أمام ممثلي منظومة الفضاء الوطنية في دولة الإمارات.",
        },
        {
            "title": "تطوير المهارات المهنية",
            "description": "بناء مهارات العمل الجماعي وحل المشكلات وإدارة المشاريع والتواصل التقني والعرض التقديمي.",
        },
        {
            "title": "جوائز وتكريم",
            "description": "التنافس على جوائز مالية وشهادات تقدير للتميز الهندسي والابتكار.",
        },
    ],
    "at_a_glance": [
        {"highlight": "المشاركة المستهدفة", "details": "نحو 500 طالب وطالبة (تقديري)"},
        {"highlight": "حجم الفريق", "details": "من 2 إلى 4 طلاب"},
        {"highlight": "الفرق المتأهلة للنهائيات", "details": "نحو 10 فرق"},
        {"highlight": "ميزانية النموذج الأولي", "details": "300 درهم إماراتي لكل فريق"},
    ],
    "eligibility_intro": "يرحب تحدي سات فورج الإمارات 2026 بالطلبة المؤهلين المسجلين في الجامعات ومؤسسات التعليم العالي في دولة الإمارات العربية المتحدة.",
    "eligibility_rows": [
        {"label": "القيد الدراسي", "requirement": "مقيد حالياً في إحدى الجامعات أو مؤسسات التعليم العالي في دولة الإمارات"},
        {"label": "العمر", "requirement": "من 16 إلى 24 عاماً (شاملاً)"},
        {"label": "حجم الفريق", "requirement": "من 2 إلى 4 طلاب"},
        {"label": "تمثيل مواطني الدولة", "requirement": "يجب أن يضم كل فريق طالباً إماراتياً واحداً على الأقل"},
        {"label": "الفرق المشتركة بين الجامعات", "requirement": "مسموح بتشكيل فرق من جامعات أو فروع جامعية مختلفة"},
        {"label": "التخصصات الأكاديمية", "requirement": "مفتوح لجميع التخصصات، مع تشجيع طلبة الهندسة والتخصصات التقنية"},
    ],
    "eligibility_note": "يُشجع بشكل خاص طلبة الهندسة الكهربائية، وهندسة الحاسوب، والهندسة الميكانيكية، وهندسة الطيران والفضاء، والهندسة الطبية الحيوية، والبرامج ذات الصلة، كما نرحب بالفرق متعددة التخصصات.",
    "journey_stages": [
        {
            "stage": "المرحلة ١",
            "title": "تشكيل الفريق والتسجيل",
            "description": "تكوين فريق مؤهل من 2 إلى 4 طلاب وإتمام التسجيل الرسمي.",
        },
        {
            "stage": "المرحلة ٢",
            "title": "التعلم والتحضير",
            "description": "الدخول إلى منصة سبيس بوينت التعليمية وحضور الجلسات التدريبية واستكشاف موارد هندسة الأقمار الصناعية.",
        },
        {
            "stage": "المرحلة ٣",
            "title": "التصميم والمحاكاة",
            "description": "تطوير مفهوم المهمة والدوائر الإلكترونية والنموذج ثلاثي الأبعاد والمحاكاة ولوحة عرض البيانات.",
        },
        {
            "stage": "المرحلة ٤",
            "title": "البناء والتأهل",
            "description": "بناء نموذج أولي عملي وربط بيانات الحساسات بلوحة العرض التفاعلية وتقديم الوثائق التقنية.",
        },
        {
            "stage": "المرحلة ٥",
            "title": "المعرض الختامي والتحكيم",
            "description": "تأهل نحو 10 فرق لتطوير نماذجها الأولية حضورياً واستعراضها أمام لجنة التحكيم.",
        },
    ],
    "timeline": [
        {"date": "11 أكتوبر", "milestone": "فتح باب تسجيل الفرق الطلابية"},
        {"date": "15 أكتوبر", "milestone": "الانطلاق الرسمي — مسرح جامعة أبوظبي، حرم العين"},
        {"date": "15–21 أكتوبر", "milestone": "التهيئة والتدريب عبر منصة SpacePoint"},
        {"date": "21 أكتوبر، 6:00 مساءً", "milestone": "الموعد النهائي للتسجيل"},
        {"date": "22 أكتوبر، 5:00 مساءً", "milestone": "الجلسة التعريفية والتوضيحية الأولى عبر الإنترنت (60 دقيقة)"},
        {"date": "26 أكتوبر، 5:00 مساءً", "milestone": "الجلسة التوضيحية الثانية والأسئلة والأجوبة عبر الإنترنت (60 دقيقة)"},
        {"date": "30 أكتوبر، 12:00 ظهراً", "milestone": "تسليم متطلبات المرحلة الأولى (التصميم الرقمي والمحاكاة)"},
        {"date": "4 نوفمبر، 12:00 ظهراً", "milestone": "التسليم النهائي لمرحلة التأهل"},
        {"date": "6 نوفمبر", "milestone": "إعلان نحو 10 فرق متأهلة للتصفيات النهائية"},
        {"date": "9–10 نوفمبر (قيد التأكيد)، 9 ص – 2 م", "milestone": "الإعداد الحضوري والإرشاد التقني للفرق المتأهلة"},
        {"date": "11 نوفمبر (قيد التأكيد)، 9 ص – 2 م", "milestone": "المعرض الختامي والتحكيم وتوزيع الجوائز"},
    ],
    "timeline_note": "جميع الأوقات بتوقيت دولة الإمارات العربية المتحدة. المواعيد الحضورية النهائية مبدئية وقابلة للتأكيد. قد يُغلق باب التسجيل مبكراً عند اكتمال العدد المستهدف.",
    "deliverables": [
        {
            "phase": "المرحلة الأولى — التصميم الرقمي والمحاكاة",
            "deadline": "30 أكتوبر 2026، الساعة 12:00 ظهراً",
            "items": [
                "الدائرة الإلكترونية والمحاكاة: رابط تصميم الدائرة على Tinkercad، ومحاكاة Multisim مع تسجيل شاشة.",
                "التصميم ثلاثي الأبعاد للنموذج الأولي: نموذج ثلاثي الأبعاد باستخدام Tinkercad 3D أو Fusion 360.",
                "لوحة البيانات التفاعلية: لوحة تحكم حية تعرض بيانات المهمة أو النظام الفضائي.",
                "ملصق المسابقة (Poster): يوضح المهمة والفكرة والتصميم وأبرز المعلومات التقنية؛ رابط Canva مع صلاحية التحرير.",
            ],
        },
        {
            "phase": "المرحلة الثانية — النموذج الأولي للأجهزة والتأهل",
            "deadline": "4 نوفمبر 2026، الساعة 12:00 ظهراً",
            "items": [
                "نموذج أولي عملي للأجهزة متصل بلوحة بيانات تفاعلية لقراءة الحساسات.",
                "التقرير التقني: بنية النظام، المكونات، تصميم الدائرة، الكود البرمجي، الاختبارات والنتائج.",
                "فيديو توضيحي للنموذج الأولي يظهر عمل الأجهزة ولوحة البيانات.",
                "عرض تقديمي مسجل للفريق: بصيغة MP4 بحد أقصى خمس دقائق يغطي المهمة والتصميم والتنفيذ والنموذج والنتائج.",
                "تحديث ملصق المسابقة (عند الاقتضاء)؛ رابط Canva مع صلاحية التحرير.",
            ],
        },
    ],
    "deliverables_note": "ميزانية النموذج الأولي: يُطلب من الفرق بناء نموذج القمر الصناعي المكعب الوظيفي ضمن ميزانية لا تتجاوز 300 درهم إماراتي. يُرجى الرجوع إلى الدليل الإرشادي الرسمي للاطلاع على المتطلبات الكاملة ومعايير التقييم.",
    "awards_text": (
        "عقب تقييم تسليمات مرحلة التأهل، سيتم اختيار نحو 10 فرق متأهلة للمنافسة في النهائيات الوطنية. "
        "تشارك الفرق المتأهلة في يومين من التطوير الحضوري للنموذج الأولي والاختبار والتحسين والإرشاد التقني، "
        "يليهما يوم ثالث للعروض الحية والتحكيم والتكريم.\n\n"
        "ستحصل الفرق الفائزة على جوائز مالية وتقدير للابتكار والإنجاز الهندسي والأداء المتميز، كما يتيح المعرض الختامي "
        "فرصة التواصل المباشر مع الخبراء وممثلي منظومة الفضاء والتكنولوجيا المتقدمة في دولة الإمارات."
    ),
    "registration_text": (
        "هل أنت مستعد لتحويل أفكارك في هندسة الأقمار الصناعية إلى واقع؟ شكّل فريقك، وتأكد من استيفاء شروط الأهلية، "
        "وقدم استمارة تسجيل رسمية واحدة تتضمن البيانات الكاملة لجميع أعضاء الفريق."
    ),
    "registration_deadline": "21 أكتوبر 2026، الساعة 6:00 مساءً بتوقيت دولة الإمارات. قد يُغلق التسجيل مبكراً في حال الوصول إلى العدد المستهدف.",
    "registration_note": "نُشجع الطلبة الذين لم يشكلوا فرقاً بعد على التواصل مع المشاركين المؤهلين عبر مجموعة واتساب المخصصة لتشكيل الفرق.",
    "faqs": [
        {
            "question": "هل يمكن لطلبة من جامعات مختلفة تشكيل فريق واحد؟",
            "answer": "نعم، يُسمح بتشكيل فرق مشتركة بين جامعات أو فروع جامعية مختلفة شريطة استيفاء جميع متطلبات الأهلية.",
        },
        {
            "question": "هل يُشترط وجود طالب إماراتي في كل فريق؟",
            "answer": "نعم، يجب أن يضم كل فريق عضواً واحداً على الأقل من مواطني دولة الإمارات العربية المتحدة.",
        },
        {
            "question": "هل يمكن لطلبة التخصصات غير الهندسية المشاركة؟",
            "answer": "نعم، ترحب المسابقة بالطلبة من جميع التخصصات الأكاديمية وتشجع الفرق متعددة التخصصات.",
        },
        {
            "question": "هل نحتاج إلى خبرة سابقة في تطوير الأقمار الصناعية؟",
            "answer": "لا تُشترط خبرة سابقة؛ حيث سيتم توفير موارد تدريبية وإرشاد تقني لجميع الفرق المشاركة.",
        },
        {
            "question": "هل يتعين على الفرق بناء أجهزة فعلية (Hardware)؟",
            "answer": "نعم، يُشترط بناء نموذج أولي عملي للأجهزة متصل بلوحة عرض بيانات تفاعلية للتأهل للمرحلة النهائية.",
        },
        {
            "question": "ما هي الميزانية المسموح بها للنموذج الأولي؟",
            "answer": "300 درهم إماراتي لبناء نموذج القمر الصناعي المكعب الوظيفي.",
        },
        {
            "question": "كم عدد الفرق التي ستتأهل إلى النهائيات؟",
            "answer": "من المتوقع تأهل نحو 10 فرق إلى التصفيات النهائية.",
        },
        {
            "question": "هل مواعيد التصفيات النهائية مؤكدة؟",
            "answer": "الفترة من 9 إلى 11 نوفمبر 2026 مبدئية وقابلة للتأكيد النهائي من قِبل اللجنة المنظمة.",
        },
        {
            "question": "هل يتم توفير المواصلات أو الإقامة؟",
            "answer": "لا يتضمن الدليل الإرشادي الحالي تفاصيل حول ترتيبات المواصلات أو الإقامة؛ يُرجى المتابعة مع الجهة المنظمة.",
        },
    ],
    "partners": [
        {"name": "جامعة أبوظبي", "role": "المؤسسة المستضيفة", "logo_url": ""},
        {"name": "وكالة الإمارات للفضاء", "role": "شريك داعم", "logo_url": ""},
        {"name": "أكاديمية الفضاء الوطنية", "role": "شريك داعم", "logo_url": ""},
        {"name": "سبيس بوينت (SpacePoint)", "role": "الشريك التقني والمنصة التعليمية", "logo_url": ""},
        {"name": "الفرع الطلابي لـ IEEE بجامعة أبوظبي", "role": "شريك داعم", "logo_url": ""},
    ],
    "partners_note": "",
    "contacts": [
        {
            "name": "د. جواد يوسف",
            "role": "كلية الهندسة — قسم الهندسة الكهربائية وهندسة الحاسوب والهندسة الطبية الحيوية",
            "organization": "جامعة أبوظبي",
            "email": "jawad.yousaf@adu.ac.ae",
        },
        {
            "name": "أ. عبدالله السلماني",
            "role": "سبيس بوينت للفضاء (SpacePoint)",
            "organization": "SpacePoint",
            "email": "a.alsalmani@spacepoint.ae",
        },
    ],
    "contact_meta": [
        {"label": "المسابقة", "value": "سات فورج الإمارات 2026", "url": ""},
        {"label": "المؤسسة المستضيفة", "value": "جامعة أبوظبي — حرم العين", "url": ""},
        {"label": "استمارة التسجيل الرسمية", "value": "سجّل فريقك الآن", "url": "https://forms.cloud.microsoft/r/RB8u7Zruqt"},
        {"label": "المنصة التقنية", "value": "spacepoint.ae", "url": "https://www.spacepoint.ae"},
        {"label": "الدليل الإرشادي للمسابقة", "value": "تحميل الدليل الإرشادي (PDF)", "url": "https://drive.google.com/file/d/1SfIpUkt_aL7uePCOxZuLUz3IdRZ_8bZk/view"},
    ],
}


async def ensure_default_events_seeded(db: AsyncSession) -> None:
    """Idempotently seed World Space Week UAE ('wsw') as a MegaEvent and
    SatForge UAE 2026 ('satforge-2026') as a WebsiteEvent inside WSW so the
    platform launches pre-populated out of the box."""
    wsw = (
        await db.execute(select(MegaEvent).where(MegaEvent.slug == "wsw"))
    ).scalars().first()

    if wsw is None:
        wsw = MegaEvent(
            slug="wsw",
            country="uae",
            title="World Space Week UAE 2026",
            title_ar="أسبوع الفضاء العالمي في الإمارات ٢٠٢٦",
            subtitle="One Week. One Ecosystem. Endless Possibilities.",
            tagline="Discover. Participate. Connect. Measure Impact.",
            banner_url="/assets/img/The Mission.jpg",
            top_banner_url=None,
            date_label="October 2026 • Across All 7 Emirates",
            about_text=(
                "A public platform bringing together events, speakers, mentors, volunteers and "
                "organizations participating in World Space Week across the UAE.\n\n"
                "Discover space events across the UAE, connect with speakers and mentors, "
                "volunteer with participating organizations, or bring World Space Week to your own community."
            ),
            official_note=(
                "This platform supports outreach and coordination for World Space Week activities in the UAE. "
                "Organizers are encouraged to register their events through the official World Space Week website."
            ),
            official_url="https://www.worldspaceweek.org",
            primary_cta_label="Explore UAE Events",
            primary_cta_url="#events-directory",
            at_a_glance=[
                {"highlight": "7 Emirates", "details": "Nationwide UAE Coverage"},
                {"highlight": "Universities & Schools", "details": "Campus & Community Activities"},
                {"highlight": "Industry Mentors", "details": "Space Professionals & Experts"},
                {"highlight": "Global Initiative", "details": "Connected to World Space Week"},
            ],
            host_steps=[
                {
                    "stage": "Step 1",
                    "title": "Develop Your Event",
                    "description": "Plan a workshop, talk, competition, exhibition, panel, hackathon, or stargazing activity for your community.",
                },
                {
                    "stage": "Step 2",
                    "title": "Register Officially with WSW",
                    "description": "Register your activity on the official global World Space Week website (worldspaceweek.org).",
                },
                {
                    "stage": "Step 3",
                    "title": "Submit to the UAE Hub",
                    "description": "Sign up as a partner organization on SpacePoint and add your event so participants across the UAE can discover it.",
                },
                {
                    "stage": "Step 4",
                    "title": "Connect & Collaborate",
                    "description": "Engage speakers, mentors, and WSW UAE Space Ambassadors to support your activity.",
                },
                {
                    "stage": "Step 5",
                    "title": "Measure & Share Impact",
                    "description": "Submit your post-event outcomes to contribute to the UAE World Space Week National Impact Report.",
                },
            ],
            coordinator_info={
                "name": "Abdullah AlSalmani",
                "role": "UAE National Coordinator – World Space Week",
                "email": "a.alsalmani@spacepoint.ae",
                "note": "The UAE World Space Week Hub is an ecosystem coordination and outreach initiative supporting participation in the official World Space Week campaign.",
            },
            partners=[
                {"name": "World Space Week Association", "role": "Global Initiative", "logo_url": ""},
                {"name": "SpacePoint", "role": "UAE Ecosystem Hub Platform", "logo_url": ""},
            ],
            faqs=[
                {
                    "question": "Does this platform replace the official World Space Week registration?",
                    "answer": "No. This hub complements the official World Space Week platform by providing a UAE-specific discovery and coordination layer. Every organizer is encouraged to register their event on worldspaceweek.org first.",
                },
                {
                    "question": "How can our university, school, or organization list an event?",
                    "answer": "Organizations can sign up on the SpacePoint Portal, create their event page using our standardized template, and submit it for publication under World Space Week UAE.",
                },
                {
                    "question": "Do visitors need an account to browse events?",
                    "answer": "No. All public event listings, schedules, and registration links are openly accessible without logging in.",
                },
            ],
            default_language="en",
            ar_content=DEFAULT_WSW_AR_CONTENT,
            display_order=1,
            is_published=True,
        )
        db.add(wsw)
        await db.flush()
    else:
        if wsw.banner_url and wsw.banner_url.endswith("-cropped.png") and wsw.top_banner_url is None:
            wsw.top_banner_url = wsw.banner_url
            wsw.banner_url = "/assets/img/The Mission.jpg"
        elif wsw.banner_url is None and wsw.top_banner_url is None:
            wsw.banner_url = "/assets/img/The Mission.jpg"
        if not wsw.ar_content:
            wsw.ar_content = DEFAULT_WSW_AR_CONTENT
        if not wsw.default_language:
            wsw.default_language = "en"

    satforge = (
        await db.execute(select(WebsiteEvent).where(WebsiteEvent.slug == "satforge-2026"))
    ).scalars().first()

    if satforge is None:
        satforge = WebsiteEvent(
            slug="satforge-2026",
            mega_event_id=wsw.id,
            country="uae",
            city="Al Ain",
            event_type="competition",
            audience="Universities",
            venue_type="hybrid",
            title="SatForge UAE 2026",
            title_ar="سات فورج الإمارات 2026: التحدي الوطني للجامعات في هندسة وتصميم الأقمار الصناعية",
            subtitle="National University Satellite Engineering Challenge",
            tagline="From Campus Innovation to Future Space Missions",
            banner_url="/assets/img/The Mission.jpg",
            top_banner_url=None,
            host_org_name="Abu Dhabi University",
            date_label="11 October – 11 November 2026",
            location="Abu Dhabi University — Al Ain Campus",
            registration_url="https://forms.cloud.microsoft/r/RB8u7Zruqt",
            guidelines_url="https://drive.google.com/file/d/1SfIpUkt_aL7uePCOxZuLUz3IdRZ_8bZk/view",
            wsw_official_url="https://www.worldspaceweek.org",
            about_text=(
                "SatForge UAE 2026: National University Satellite Engineering Challenge is a nationwide "
                "university-level satellite engineering competition that brings together talented students "
                "from higher education institutions across the United Arab Emirates to design, develop, and "
                "demonstrate innovative CubeSat-inspired satellite systems.\n\n"
                "Hosted by the College of Engineering at Abu Dhabi University, with support from the UAE Space "
                "Agency, National Space Academy, SpacePoint, Research Institute for AI & Emerging Technologies, "
                "and IEEE ADU Student Branch, the competition offers an immersive, hands-on learning experience "
                "that bridges academic knowledge and practical satellite engineering.\n\n"
                "Participants progress through technical training, mission conceptualization, electronic circuit "
                "design, simulation, 3D modeling, software development, data visualization, and hardware prototyping. "
                "With guidance from space and advanced technology professionals, teams turn ideas into functional "
                "satellite prototypes.\n\n"
                "Approximately 10 outstanding teams will advance to the final stage for on-site technical "
                "preparation and a national showcase evaluated by industry experts."
            ),
            benefits=[
                {
                    "title": "Hands-on engineering experience",
                    "description": "Apply theory to mission design, simulation, electronics, programming, testing, and prototyping.",
                },
                {
                    "title": "Industry mentorship",
                    "description": "Learn from professionals working in the UAE space and advanced technology sectors.",
                },
                {
                    "title": "Interdisciplinary collaboration",
                    "description": "Work with students from diverse engineering and technical disciplines.",
                },
                {
                    "title": "National exposure",
                    "description": "Showcase solutions to representatives of the UAE space ecosystem.",
                },
                {
                    "title": "Professional development",
                    "description": "Build teamwork, problem-solving, project management, technical communication, and presentation skills.",
                },
                {
                    "title": "Awards and recognition",
                    "description": "Compete for monetary prizes and other recognition.",
                },
            ],
            at_a_glance=[
                {"highlight": "Target participation", "details": "Approximately 500 students (indicative)"},
                {"highlight": "Team size", "details": "2–4 students"},
                {"highlight": "Finalist teams", "details": "Approximately 10"},
                {"highlight": "Prototype budget", "details": "AED 300 per team"},
            ],
            eligibility_intro="SatForge UAE 2026 welcomes eligible students enrolled in universities and higher education institutions across the UAE.",
            eligibility_rows=[
                {"label": "Enrollment", "requirement": "Currently enrolled at a UAE university or higher education institution"},
                {"label": "Age", "requirement": "16–24 years inclusive"},
                {"label": "Team size", "requirement": "2–4 students"},
                {"label": "UAE national representation", "requirement": "At least one Emirati member per team"},
                {"label": "Cross-university teams", "requirement": "Permitted, including across campuses"},
                {"label": "Academic disciplines", "requirement": "Open to all disciplines; engineering and related fields encouraged"},
            ],
            eligibility_note="Participation is particularly encouraged from Electrical, Computer, Mechanical, Aerospace, and Biomedical Engineering and related programs. Multidisciplinary teams are welcome.",
            journey_stages=[
                {
                    "stage": "Stage 1",
                    "title": "Form Your Team & Register",
                    "description": "Assemble an eligible team of 2–4 students and complete registration.",
                },
                {
                    "stage": "Stage 2",
                    "title": "Learn & Prepare",
                    "description": "Access the SpacePoint learning platform, attend training, and explore satellite engineering resources.",
                },
                {
                    "stage": "Stage 3",
                    "title": "Design & Simulate",
                    "description": "Develop the mission concept, electronic circuits, 3D model, simulations, and data dashboard.",
                },
                {
                    "stage": "Stage 4",
                    "title": "Build & Qualify",
                    "description": "Construct a functional prototype, integrate sensor data with a dashboard and submit documentation.",
                },
                {
                    "stage": "Stage 5",
                    "title": "Final Showcase",
                    "description": "Approximately 10 shortlisted teams refine their prototypes and demonstrate them before judges.",
                },
            ],
            timeline=[
                {"date": "11 October", "milestone": "Student team registration opens"},
                {"date": "15 October", "milestone": "Official kick-off — Abu Dhabi University Auditorium, Al Ain Campus"},
                {"date": "15–21 October", "milestone": "SpacePoint platform onboarding"},
                {"date": "21 October, 6:00 PM", "milestone": "Registration deadline"},
                {"date": "22 October, 5:00 PM", "milestone": "First online clarification session (60 minutes)"},
                {"date": "26 October, 5:00 PM", "milestone": "Second online clarification and Q&A (60 minutes)"},
                {"date": "30 October, 12:00 PM", "milestone": "Phase 1 digital design submission"},
                {"date": "4 November, 12:00 PM", "milestone": "Final qualifier submission"},
                {"date": "6 November", "milestone": "Announcement of approximately 10 finalist teams"},
                {"date": "9–10 November (TBC), 9 AM–2 PM", "milestone": "On-site preparation and mentoring"},
                {"date": "11 November (TBC), 9 AM–2 PM", "milestone": "Final showcase and judging"},
            ],
            timeline_note="All times are UAE local time. Final on-site dates are tentative. Registration may close early when the participation target is reached.",
            deliverables=[
                {
                    "phase": "Phase 1 — Digital Design & Simulation",
                    "deadline": "30 October 2026, 12:00 PM (noon)",
                    "items": [
                        "Electronic circuit and simulation: Tinkercad circuit design link, Multisim simulation and screen recording.",
                        "3D prototype design: 3D model using Tinkercad 3D or Fusion 360.",
                        "Interactive dashboard: Live dashboard displaying relevant satellite mission or system data.",
                        "Competition poster: Mission, concept, design and key technical information; Canva link with editor access.",
                    ],
                },
                {
                    "phase": "Phase 2 — Hardware Prototype & Qualification",
                    "deadline": "4 November 2026, 12:00 PM (noon)",
                    "items": [
                        "Functional hardware prototype connected to an interactive sensor-data dashboard.",
                        "Technical report: System architecture, components, circuit design, code, testing and results.",
                        "Prototype demonstration video showing the working hardware and dashboard.",
                        "Recorded team presentation: MP4, maximum five minutes, covering mission, design, implementation, prototype and results.",
                        "Updated competition poster, where applicable; Canva link with editor access.",
                    ],
                },
            ],
            deliverables_note="Prototype budget: Teams are challenged to build their functional CubeSat model within AED 300. Refer to the official guidelines for full requirements and early/late submission scoring adjustments.",
            awards_text=(
                "Following evaluation of qualifier submissions, approximately 10 finalist teams will be selected "
                "for the national final competition. Finalists participate in two days of on-site prototype development, "
                "testing, refinement and mentoring, followed by a third day of live demonstrations, judging and recognition.\n\n"
                "Winning teams will receive monetary prizes and other recognition for innovation, engineering achievement "
                "and competition performance. The final showcase provides exposure to professionals and representatives "
                "of the UAE space and advanced technology ecosystem."
            ),
            registration_text=(
                "Ready to turn your satellite engineering ideas into reality? Form your team, confirm eligibility, "
                "and submit one official registration form containing complete details for all team members."
            ),
            registration_deadline="21 October 2026, 6:00 PM UAE time. Registration may close earlier if the participation target is reached.",
            whatsapp_url="",
            registration_note="Students without a team are encouraged to connect with eligible participants through the team-formation WhatsApp group.",
            faqs=[
                {
                    "question": "Can students from different universities form one team?",
                    "answer": "Yes. Cross-university and cross-campus teams are permitted if all eligibility requirements are satisfied.",
                },
                {
                    "question": "Is an Emirati student required in each team?",
                    "answer": "Yes. Each team must include at least one UAE national (Emirati) member.",
                },
                {
                    "question": "Can students from non-engineering disciplines participate?",
                    "answer": "Yes. The competition welcomes all academic disciplines and encourages multidisciplinary teams.",
                },
                {
                    "question": "Do we need previous satellite development experience?",
                    "answer": "Previous experience is not listed as an eligibility requirement. Training resources and technical guidance are provided.",
                },
                {
                    "question": "Do teams need to build actual hardware?",
                    "answer": "Yes. A functional hardware prototype connected to an interactive data dashboard is required for qualification.",
                },
                {
                    "question": "What is the allowed prototype budget?",
                    "answer": "AED 300 for a functional CubeSat model.",
                },
                {
                    "question": "How many teams will reach the finals?",
                    "answer": "Approximately 10 teams are expected to be shortlisted.",
                },
                {
                    "question": "Are the final dates confirmed?",
                    "answer": "No. 9–11 November 2026 are tentative, subject to confirmation.",
                },
                {
                    "question": "Are transportation and accommodation provided?",
                    "answer": "The supplied competition guidelines do not specify transportation or accommodation arrangements; confirm with organizers.",
                },
            ],
            partners=[
                {"name": "Abu Dhabi University", "role": "Host Institution", "logo_url": ""},
                {"name": "UAE Space Agency", "role": "Supporting Partner", "logo_url": ""},
                {"name": "National Space Academy", "role": "Supporting Partner", "logo_url": ""},
                {"name": "SpacePoint", "role": "Technical Platform Partner", "logo_url": ""},
                {"name": "IEEE ADU Student Branch", "role": "Supporting Partner", "logo_url": ""},
            ],
            partners_note="",
            contacts=[
                {
                    "name": "Dr. Jawad Yousaf",
                    "role": "College of Engineering, Electrical, Computer and Biomedical Engineering Department",
                    "organization": "Abu Dhabi University",
                    "email": "jawad.yousaf@adu.ac.ae",
                },
                {
                    "name": "Mr. Abdullah Salmani",
                    "role": "SpacePoint Space",
                    "organization": "SpacePoint",
                    "email": "a.alsalmani@spacepoint.ae",
                },
            ],
            contact_meta=[
                {"label": "Competition", "value": "SatForge UAE 2026", "url": ""},
                {"label": "Host institution", "value": "Abu Dhabi University — Al Ain Campus", "url": ""},
                {"label": "Official Registration Form", "value": "Register Your Team", "url": "https://forms.cloud.microsoft/r/RB8u7Zruqt"},
                {"label": "Technical Platform", "value": "spacepoint.ae", "url": "https://www.spacepoint.ae"},
                {"label": "Competition Guidelines", "value": "Download PDF Guidelines", "url": "https://drive.google.com/file/d/1SfIpUkt_aL7uePCOxZuLUz3IdRZ_8bZk/view"},
            ],
            default_language="en",
            ar_content=DEFAULT_SATFORGE_AR_CONTENT,
            display_order=1,
            is_published=True,
        )
        db.add(satforge)
    else:
        if satforge.banner_url and satforge.banner_url.endswith("-cropped.png") and satforge.top_banner_url is None:
            satforge.top_banner_url = satforge.banner_url
            satforge.banner_url = "/assets/img/The Mission.jpg"
        elif satforge.banner_url is None and satforge.top_banner_url is None:
            satforge.banner_url = "/assets/img/The Mission.jpg"
        if not satforge.ar_content:
            satforge.ar_content = DEFAULT_SATFORGE_AR_CONTENT
        if not satforge.default_language:
            satforge.default_language = "en"

    await db.commit()


async def serialize_mega_events(
    db: AsyncSession, rows: list[MegaEvent], published_only_counts: bool = False
) -> list[dict]:
    if not rows:
        return []
    ids = [r.id for r in rows]
    stmt = (
        select(WebsiteEvent.mega_event_id, func.count(WebsiteEvent.id))
        .where(WebsiteEvent.mega_event_id.in_(ids))
    )
    if published_only_counts:
        stmt = stmt.where(WebsiteEvent.is_published.is_(True))
    stmt = stmt.group_by(WebsiteEvent.mega_event_id)
    counts = dict((await db.execute(stmt)).all())

    out = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d["events_count"] = counts.get(r.id, 0)
        out.append(d)
    return out


async def serialize_website_events(db: AsyncSession, rows: list[WebsiteEvent]) -> list[dict]:
    if not rows:
        return []
    mega_ids = {r.mega_event_id for r in rows if r.mega_event_id}
    org_ids = {r.organization_id for r in rows if r.organization_id}

    megas_by_id: dict[UUID, MegaEvent] = {}
    if mega_ids:
        megas = (await db.execute(select(MegaEvent).where(MegaEvent.id.in_(mega_ids)))).scalars().all()
        megas_by_id = {m.id: m for m in megas}

    orgs_by_id: dict[UUID, Organization] = {}
    if org_ids:
        orgs = (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()
        orgs_by_id = {o.id: o for o in orgs}

    out = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        mega = megas_by_id.get(r.mega_event_id) if r.mega_event_id else None
        org = orgs_by_id.get(r.organization_id) if r.organization_id else None
        d["mega_event_slug"] = mega.slug if mega else None
        d["mega_event_title"] = mega.title if mega else None
        d["organization_name"] = org.name_latin if org else r.host_org_name
        out.append(d)
    return out
