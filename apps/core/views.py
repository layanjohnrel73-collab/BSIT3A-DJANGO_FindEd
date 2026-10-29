from datetime import timedelta
import re

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

User = get_user_model()

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=1)
INVALID_LOGIN_MESSAGE = 'Invalid username or password.'
LOCKED_MESSAGE = 'Too many failed attempts. Locked for 1 minute.'


def _reset_lock_state(request):
    request.session['failed_attempts'] = 0
    request.session['lock_time'] = None


def _get_lock_state(request):
    failed_attempts = request.session.get('failed_attempts', 0)
    lock_time = request.session.get('lock_time')

    if not lock_time:
        return failed_attempts, None

    try:
        unlock_time = timezone.datetime.fromisoformat(lock_time)
    except (TypeError, ValueError):
        _reset_lock_state(request)
        return 0, None

    if timezone.now() < unlock_time:
        remaining = int((unlock_time - timezone.now()).total_seconds())
        return failed_attempts, remaining

    _reset_lock_state(request)
    return 0, None


def _set_lock_state(request):
    lock_until = timezone.now() + LOCK_DURATION
    request.session['failed_attempts'] = MAX_FAILED_ATTEMPTS
    request.session['lock_time'] = lock_until.isoformat()
    return int(LOCK_DURATION.total_seconds())


def _validate_registration_data(data):
    errors = {}

    username = data.get('username', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not username:
        errors['username'] = 'Username is required.'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Username already taken.'

    if not first_name:
        errors['first_name'] = 'First name is required.'

    if not last_name:
        errors['last_name'] = 'Last name is required.'

    if not email:
        errors['email'] = 'Email is required.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            if User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered.'

    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters.'
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)

    if password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match.'

    return errors


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    failed_attempts, remaining = _get_lock_state(request)
    if remaining is not None:
        messages.error(request, f'Too many failed attempts. Try again in {remaining} seconds.')
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    if request.method == 'GET':
        return render(request, 'auth/login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    user = authenticate(request, username=username, password=password)

    if user is not None:
        _reset_lock_state(request)
        login(request, user)
        return redirect('dashboard')

    failed_attempts += 1
    request.session['failed_attempts'] = failed_attempts
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        remaining = _set_lock_state(request)
        messages.error(request, LOCKED_MESSAGE)
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts
    messages.error(request, f'{INVALID_LOGIN_MESSAGE} {remaining_attempts} attempts remaining.')
    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# Public guide data — no login needed so new students can find rooms.
# Starter campus data for Kabankalan Catholic College (KCC)
# Guanzon St., Brgy. 1, Kabankalan City. Edit freely — later move to DB.
# Real KCC layout (from school history + student guides):
# College = 2 storeys | HS = 3 storeys, chapel in front | Elementary = 2
# storeys beside canteen | St. Columban Arts Center + annex (canteen G/F,
# library upper) | Gym. Room lists are starters — correct me anytime.
CAMPUS_BUILDINGS = [
        {
            "id": "main",
            "name": "Admin Building",
            "short": "ADMIN",
            "type": "office",
            "floors": 2,
            "desc": "Registrar, Accounting, President's Office. Beside the Main Gate on Guanzon St.",
            "rooms": [
                {"code": "Registrar", "floor": "G/F", "detail": "Enrollment, records, Form 137"},
                {"code": "Accounting", "floor": "G/F", "detail": "Payments, balances"},
                {"code": "Guidance", "floor": "2F", "detail": "Counseling, strand advice"},
                {"code": "President's Office", "floor": "2F", "detail": "Admin"},
            ],
        },
        {
            "id": "college",
            "name": "College Department (BSIT Home)",
            "short": "COLLEGE",
            "type": "classroom",
            "floors": 2,
            "desc": "2-storey building: COED, CBA, CAS, CCJ — Educ, Accountancy, Business, IT and more. BSIT 3A is here.",
            "rooms": [
                {"code": "BSBA 1-A", "floor": "G/F", "detail": "Business Admin"},
                {"code": "BSCRIM 1-A", "floor": "G/F", "detail": "Criminology"},
                {"code": "BEED 1-A", "floor": "G/F", "detail": "Teacher Education"},
                {"code": "BSIT 1-A", "floor": "2F", "detail": "IT • Lab beside"},
                {"code": "BSIT 2-A", "floor": "2F", "detail": "IT"},
                {"code": "BSIT 3-A", "floor": "2F", "detail": "IT • Capstone room ★"},
                {"code": "BSA 2-A", "floor": "2F", "detail": "Accountancy"},
                {"code": "BS Psych 2-A", "floor": "2F", "detail": "Psychology"},
                {"code": "BSED 3-A", "floor": "2F", "detail": "Teacher Education"},
                {"code": "LAB 1", "floor": "2F", "detail": "Computer laboratory"},
                {"code": "LAB 4", "floor": "2F", "detail": "Computer laboratory"},
                {"code": "LAB 6", "floor": "2F", "detail": "Computer laboratory • Networking"},
                {"code": "LAB 7", "floor": "2F", "detail": "Computer laboratory • Database"},
                {"code": "CMAT 104", "floor": "G/F", "detail": "Lecture room • Quantitative Methods"},
                {"code": "CMAT 303", "floor": "3F", "detail": "Lecture room • Theology"},
            ],
        },
        {
            "id": "hs",
            "name": "High School Department",
            "short": "HIGH SCHOOL",
            "type": "classroom",
            "floors": 3,
            "desc": "3-storey building with the Chapel in front. JHS + SHS. Flag ceremony every Monday.",
            "rooms": [
                {"code": "Grade 7-A", "floor": "G/F", "detail": "7 sections in Grade 7"},
                {"code": "Grade 7-B", "floor": "G/F", "detail": "7 sections in Grade 7"},
                {"code": "Grade 7-C", "floor": "G/F", "detail": "7 sections in Grade 7"},
                {"code": "Grade 7-D", "floor": "G/F", "detail": "7 sections in Grade 7"},
                {"code": "Grade 7-E", "floor": "G/F", "detail": "7 sections in Grade 7"},
                {"code": "Grade 7-F", "floor": "G/F", "detail": "7 sections in Grade 7"},
                {"code": "Grade 7-G", "floor": "G/F", "detail": "7 sections in Grade 7"},
                {"code": "Grade 8-A", "floor": "2F", "detail": "5 sections in Grade 8"},
                {"code": "Grade 8-B", "floor": "2F", "detail": "5 sections in Grade 8"},
                {"code": "Grade 8-C", "floor": "2F", "detail": "5 sections in Grade 8"},
                {"code": "Grade 8-D", "floor": "2F", "detail": "5 sections in Grade 8"},
                {"code": "Grade 8-E", "floor": "2F", "detail": "5 sections in Grade 8"},
                {"code": "Grade 9-A", "floor": "2F", "detail": "4 sections in Grade 9"},
                {"code": "Grade 9-B", "floor": "2F", "detail": "4 sections in Grade 9"},
                {"code": "Grade 9-C", "floor": "2F", "detail": "4 sections in Grade 9"},
                {"code": "Grade 9-D", "floor": "2F", "detail": "4 sections in Grade 9"},
                {"code": "Grade 10-A", "floor": "3F", "detail": "4 sections in Grade 10"},
                {"code": "Grade 10-B", "floor": "3F", "detail": "4 sections in Grade 10"},
                {"code": "Grade 10-C", "floor": "3F", "detail": "4 sections in Grade 10"},
                {"code": "Grade 10-D", "floor": "3F", "detail": "4 sections in Grade 10"},
                {"code": "STEM 11-A", "floor": "3F", "detail": "Senior High • 7 sections all tracks"},
                {"code": "ABM 11-B", "floor": "3F", "detail": "Senior High"},
                {"code": "HUMSS 12-A", "floor": "3F", "detail": "Senior High"},
                {"code": "TVL 12", "floor": "3F", "detail": "Senior High TVL"},
            ],
        },
        {
            "id": "elem",
            "name": "Elementary Department",
            "short": "ELEMENTARY",
            "type": "classroom",
            "floors": 2,
            "desc": "2-storey building beside the school canteen. Grades 1–6, 2 sections each. Flag ceremony Mondays.",
            "rooms": [
                {"code": "Grade 1-A", "floor": "G/F", "detail": "2 sections per grade"},
                {"code": "Grade 1-B", "floor": "G/F", "detail": "2 sections per grade"},
                {"code": "Grade 2-A", "floor": "G/F", "detail": "2 sections per grade"},
                {"code": "Grade 2-B", "floor": "G/F", "detail": "2 sections per grade"},
                {"code": "Grade 3-A", "floor": "G/F", "detail": "2 sections per grade"},
                {"code": "Grade 3-B", "floor": "G/F", "detail": "2 sections per grade"},
                {"code": "Grade 4-A", "floor": "2F", "detail": "2 sections per grade"},
                {"code": "Grade 4-B", "floor": "2F", "detail": "2 sections per grade"},
                {"code": "Grade 5-A", "floor": "2F", "detail": "2 sections per grade"},
                {"code": "Grade 5-B", "floor": "2F", "detail": "2 sections per grade"},
                {"code": "Grade 6-A", "floor": "2F", "detail": "2 sections per grade"},
                {"code": "Grade 6-B", "floor": "2F", "detail": "2 sections per grade"},
            ],
        },
        {
            "id": "arts",
            "name": "St. Columban Arts Center",
            "short": "ARTS CENTER",
            "type": "assembly",
            "floors": 1,
            "desc": "Socio-cultural venue for school activities — KCCians and community events.",
            "rooms": [
                {"code": "Main Hall", "floor": "G/F", "detail": "Programs, Masses, graduations"},
                {"code": "Stage", "floor": "G/F", "detail": "Performances"},
            ],
        },
        {
            "id": "annex",
            "name": "Annex (Canteen + Library)",
            "short": "ANNEX",
            "type": "office",
            "floors": 2,
            "desc": "Behind the Arts Center: college canteen + textbook center on the ground floor, College library upstairs.",
            "rooms": [
                {"code": "Food Stalls", "floor": "G/F", "detail": "Canteen • snacks & lunch"},
                {"code": "Textbook Center", "floor": "G/F", "detail": "Books & supplies"},
                {"code": "Reading Hall", "floor": "2F", "detail": "Library • Open 8am–6pm"},
                {"code": "E-Library", "floor": "2F", "detail": "PCs, WiFi"},
            ],
        },
        {
            "id": "chapel",
            "name": "Chapel",
            "short": "CHAPEL",
            "type": "faith",
            "floors": 1,
            "desc": "In front of the High School building. Daily rosary, First Friday Mass.",
            "rooms": [
                {"code": "Main Sanctuary", "floor": "G/F", "detail": "200 seats"},
            ],
        },
        {
            "id": "gym",
            "name": "KCC Gym",
            "short": "GYM",
            "type": "assembly",
            "floors": 1,
            "desc": "Intramurals, Hinugyaw, sports. South-east side of campus.",
            "rooms": [
                {"code": "Main Court", "floor": "G/F", "detail": "Basketball / volleyball"},
                {"code": "Stage", "floor": "G/F", "detail": "Programs"},
                {"code": "PE Room", "floor": "G/F", "detail": "Equipment"},
            ],
        },
]

# Real KCC anchor (OpenStreetMap): Guanzon St., Brgy. 1, Kabankalan City.
KCC_GATE = [9.997965, 122.814818]

CAMPUS_PINS = {
    'main': [9.997740, 122.814635],
    'college': [9.997605, 122.814315],
    'arts': [9.997650, 122.814910],
    'hs': [9.997605, 122.815321],
    'annex': [9.997380, 122.814910],
    'chapel': [9.997335, 122.815321],
    'elem': [9.997065, 122.814315],
    'gym': [9.997020, 122.815276],
}

# Starter campus drive paths (lat, lng) from the Main Gate to each building.
CAMPUS_PATHS = {
    'main': [KCC_GATE, [9.997850, 122.814800], [9.997850, 122.814700], [9.997740, 122.814635]],
    'college': [KCC_GATE, [9.997850, 122.814800], [9.997850, 122.814450], [9.997700, 122.814380], [9.997605, 122.814315]],
    'arts': [KCC_GATE, [9.997850, 122.814818], [9.997850, 122.814900], [9.997720, 122.814910], [9.997650, 122.814910]],
    'hs': [KCC_GATE, [9.997850, 122.814818], [9.997850, 122.815250], [9.997700, 122.815300], [9.997605, 122.815321]],
    'annex': [KCC_GATE, [9.997850, 122.814818], [9.997850, 122.814900], [9.997550, 122.814910], [9.997380, 122.814910]],
    'chapel': [KCC_GATE, [9.997850, 122.814818], [9.997850, 122.815250], [9.997450, 122.815300], [9.997335, 122.815321]],
    'elem': [KCC_GATE, [9.997850, 122.814800], [9.997850, 122.814450], [9.997300, 122.814380], [9.997065, 122.814315]],
    'gym': [KCC_GATE, [9.997850, 122.814818], [9.997850, 122.815180], [9.997300, 122.815240], [9.997020, 122.815276]],
}


def home(request):
    return render(request, 'home.html', {'gate': KCC_GATE})


def ride_view(request):
    """Real Time GPS Tracker: live device position, trail recording, and classroom routing."""
    context = {
        'buildings': CAMPUS_BUILDINGS,
        'pins': CAMPUS_PINS,
        'paths': CAMPUS_PATHS,
        'gate': KCC_GATE,
        'subjects': SUBJECTS,
        'selected_subject': request.GET.get('subject', '').strip(),
    }
    return render(request, 'ride.html', context)


def street_view(request):
    """3D street viewer with extruded OpenStreetMap buildings and a walkable campus camera."""
    context = {
        'buildings': CAMPUS_BUILDINGS,
        'pins': CAMPUS_PINS,
        'paths': CAMPUS_PATHS,
        'gate': KCC_GATE,
    }
    return render(request, 'street.html', context)


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/register.html')

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
    }

    errors = _validate_registration_data(form_data)
    if errors:
        return render(request, 'auth/register.html', {'errors': errors, 'form_data': form_data})

    user = User.objects.create_user(
        username=form_data['username'].strip(),
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
        password=form_data['password'],
    )
    login(request, user)
    return redirect('dashboard')


# --- Classroom Finder lookup (matches assignment spec) ---
# Spec: student enters e.g. "IT 2-101" and system displays
# Building / Floor / Room / Nearby.
BUILDING_LOOKUP = {
    'IT': {
        'building': 'Information Technology Building',
        'nearby': 'Staircase / Laboratory / Office',
        'desc': 'College Department — BSIT rooms and computer labs.',
    },
    'BSIT': {
        'building': 'Information Technology Building',
        'nearby': 'Staircase / Laboratory / Office',
        'desc': 'College Department — BSIT rooms and computer labs.',
    },
    'BSA': {
        'building': 'Accountancy Building',
        'nearby': 'Staircase / Registrar / Canteen',
        'desc': 'College Department — Accountancy rooms.',
    },
    'BSBA': {
        'building': 'Business Administration Building',
        'nearby': 'Staircase / Library / Canteen',
        'desc': 'College Department — Business Admin rooms.',
    },
    'BEED': {
        'building': 'Teacher Education Building',
        'nearby': 'Staircase / Library / Guidance',
        'desc': 'College Department — Education rooms.',
    },
    'BSED': {
        'building': 'Teacher Education Building',
        'nearby': 'Staircase / Library / Guidance',
        'desc': 'College Department — Education rooms.',
    },
    'BSCRIM': {
        'building': 'Criminology Building',
        'nearby': 'Staircase / Gym / Office',
        'desc': 'College Department — Criminology rooms.',
    },
    'HS': {
        'building': 'High School Department',
        'nearby': 'Chapel / Staircase / Canteen',
        'desc': '3-storey building with the Chapel in front.',
    },
    'ELEM': {
        'building': 'Elementary Department',
        'nearby': 'Canteen / Staircase / Playground',
        'desc': '2-storey building beside the school canteen.',
    },
    'LAB': {
        'building': 'Information Technology Building',
        'nearby': 'Staircase / Laboratory / Office',
        'desc': 'College computer laboratories.',
    },
    'CMAT': {
        'building': 'CMAT Building',
        'nearby': 'Staircase / Canteen / Office',
        'desc': 'Lecture rooms — CMAT wing.',
    },
}

# BSIT-3A class schedule (from student timetable screenshot).
CLASS_SCHEDULE = [
    {'day': 'Monday', 'time': '7:30-8:30am', 'code': 'IT302', 'room': 'LAB 6', 'instructor': 'Mr. Azuelo', 'title': 'Networking 2'},
    {'day': 'Monday', 'time': '9:10-10:30am', 'code': 'IT304', 'room': 'LAB 4', 'instructor': 'Ms. Israel', 'title': 'Social and Professional Issues 1'},
    {'day': 'Monday', 'time': '10:30-11:30am', 'code': 'IT303', 'room': 'LAB 7', 'instructor': 'Mr. Suarez', 'title': 'Advanced Database Systems'},
    {'day': 'Monday', 'time': '1:00-2:00pm', 'code': 'ITE107', 'room': 'LAB 6', 'instructor': 'Mr. Azuelo', 'title': 'Web Systems and Technologies 2'},
    {'day': 'Monday', 'time': '2:00-3:00pm', 'code': 'IT301', 'room': 'CMAT 104', 'instructor': 'Mr. Erillo', 'title': 'Quantitative Methods'},
    {'day': 'Tuesday', 'time': '8:00-11:00am', 'code': 'ITE107', 'room': 'LAB 6', 'instructor': 'Mr. Azuelo', 'title': 'Web Systems and Technologies 2'},
    {'day': 'Tuesday', 'time': '1:30-2:30pm', 'code': 'IT303', 'room': 'LAB 7', 'instructor': 'Mr. Suarez', 'title': 'Advanced Database Systems'},
    {'day': 'Tuesday', 'time': '2:30-3:30pm', 'code': 'IT304', 'room': 'LAB 4', 'instructor': 'Ms. Israel', 'title': 'Social and Professional Issues 1'},
    {'day': 'Wednesday', 'time': '7:30-10:30am', 'code': 'IT302', 'room': 'LAB 6', 'instructor': 'Mr. Azuelo', 'title': 'Networking 2'},
    {'day': 'Wednesday', 'time': '10:30-11:30am', 'code': 'IT303', 'room': 'LAB 7', 'instructor': 'Mr. Suarez', 'title': 'Advanced Database Systems'},
    {'day': 'Wednesday', 'time': '2:00-3:00pm', 'code': 'IT301', 'room': 'CMAT 104', 'instructor': 'Mr. Erillo', 'title': 'Quantitative Methods'},
    {'day': 'Thursday', 'time': '7:30-8:30am', 'code': 'IT302', 'room': 'LAB 6', 'instructor': 'Mr. Azuelo', 'title': 'Networking 2'},
    {'day': 'Thursday', 'time': '8:30-10:30am', 'code': 'ITE106', 'room': 'LAB 1', 'instructor': 'Ms. Israel', 'title': 'Information Assurance and Security 2'},
    {'day': 'Thursday', 'time': '10:30-11:30am', 'code': 'ITE107', 'room': 'LAB 6', 'instructor': 'Mr. Azuelo', 'title': 'Web Systems and Technologies 2'},
    {'day': 'Thursday', 'time': '1:30-2:30pm', 'code': 'IT303', 'room': 'LAB 7', 'instructor': 'Mr. Suarez', 'title': 'Advanced Database Systems'},
    {'day': 'Friday', 'time': '7:30-10:30am', 'code': 'ITE106', 'room': 'LAB 1', 'instructor': 'Ms. Israel', 'title': 'Information Assurance and Security 2'},
    {'day': 'Friday', 'time': '10:30-11:30am', 'code': 'IT303', 'room': 'LAB 7', 'instructor': 'Mr. Suarez', 'title': 'Advanced Database Systems'},
    {'day': 'Friday', 'time': '1:00-2:00pm', 'code': 'IT304', 'room': 'LAB 4', 'instructor': 'Ms. Israel', 'title': 'Social and Professional Issues 1'},
    {'day': 'Friday', 'time': '2:00-3:00pm', 'code': 'IT301', 'room': 'CMAT 104', 'instructor': 'Mr. Erillo', 'title': 'Quantitative Methods'},
    {'day': 'Friday', 'time': '5:00-7:00pm', 'code': 'Theology 5', 'room': 'CMAT 303', 'instructor': 'Mr. Glemon', 'title': 'Moral Theology'},
]

SCHEDULE_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

# One walk-mode destination per subject, mapped to the building that holds its room.
SUBJECTS = []
_subject_index = {}
for _s in CLASS_SCHEDULE:
    _item = _subject_index.get(_s['code'])
    if _item is None:
        _item = {
            'code': _s['code'],
            'title': _s['title'],
            'room': _s['room'],
            'building': 'college',
            'days': [],
        }
        _subject_index[_s['code']] = _item
        SUBJECTS.append(_item)
    if _s['day'] not in _item['days']:
        _item['days'].append(_s['day'])

FLOOR_NAMES = {
    '1': '1st Floor',
    '2': '2nd Floor',
    '3': '3rd Floor',
    '4': '4th Floor',
    'G': 'Ground Floor',
}

# Matches "IT 2-101", "IT 2 101", "BSIT 3-A", "Grade 7-A"
CODE_PATTERN = re.compile(
    r'^\s*(?P<bldg>[A-Za-z]+)\s*(?P<floor>\d)?\s*[- ]?\s*(?P<room>[\w\-]+)\s*$'
)


def find_classroom(query):
    """Parse a room code and return Building/Floor/Room/Nearby dict, or None."""
    if not query or not query.strip():
        return None
    raw = query.strip()
    upper = raw.upper()

    # 0. Lab/lecture rooms e.g. LAB 6, LAB6, CMAT 104, CMAT104
    m0 = re.match(r'^\s*(LAB|CMAT)\s*(\d+)\s*$', upper)
    if m0:
        bldg_code, room_num = m0.groups()
        info = BUILDING_LOOKUP.get(bldg_code)
        if info:
            return {
                'query': raw,
                'code': f'{bldg_code} {room_num}',
                'building': info['building'],
                'floor': '2nd Floor' if bldg_code == 'LAB' else 'Ground Floor',
                'room': room_num,
                'nearby': info['nearby'],
                'desc': info['desc'],
            }

    # 1. Direct "BLDG FLOOR-ROOM" e.g. IT 2-101
    m = re.match(r'^\s*([A-Z]+)\s+(\d)\s*[- ]\s*(\d+[A-Z]?)\s*$', upper)
    if m:
        bldg_code, floor_num, room_num = m.groups()
        info = BUILDING_LOOKUP.get(bldg_code)
        if info:
            return {
                'query': raw,
                'code': f'{bldg_code} {floor_num}-{room_num}',
                'building': info['building'],
                'floor': FLOOR_NAMES.get(floor_num, f'{floor_num} Floor'),
                'room': room_num,
                'nearby': info['nearby'],
                'desc': info['desc'],
            }

    # 2. Known room codes e.g. BSIT 3-A, Grade 7-A, STEM 11-A
    m2 = CODE_PATTERN.match(raw)
    if m2:
        bldg = m2.group('bldg').upper()
        info = BUILDING_LOOKUP.get(bldg)
        if info:
            floor_num = m2.group('floor') or ''
            room = m2.group('room') or ''
            floor_label = FLOOR_NAMES.get(floor_num, f'{floor_num} Floor' if floor_num else 'Ground Floor')
            return {
                'query': raw,
                'code': raw.upper(),
                'building': info['building'],
                'floor': floor_label,
                'room': room,
                'nearby': info['nearby'],
                'desc': info['desc'],
            }

    return None


def dashboard_view(request):
    """Public dashboard: hero search (room/subject) + weekly schedule. No login needed."""

    q = request.GET.get('q', '').strip()
    day = request.GET.get('day', '').strip()
    result = find_classroom(q) if q else None
    not_found = False
    schedule = CLASS_SCHEDULE
    if q and result is None:
        # Subject search: match code/title/instructor/room/day
        ql = q.lower()
        matched = [s for s in CLASS_SCHEDULE if ql in f"{s['code']} {s['title']} {s['instructor']} {s['room']} {s['day']}".lower()]
        if matched:
            schedule = matched
        else:
            not_found = True
    if day in SCHEDULE_DAYS:
        schedule = [s for s in schedule if s['day'] == day]

    context = {
        'q': q,
        'day': day,
        'days': SCHEDULE_DAYS,
        'schedule': schedule,
        'result': result,
        'not_found': not_found,
        'total_subjects': len({s['code'] for s in CLASS_SCHEDULE}),
        'total_classes': len(CLASS_SCHEDULE),
    }
    return render(request, 'dashboard.html', context)
