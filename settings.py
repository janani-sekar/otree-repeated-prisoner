from os import environ

SESSION_CONFIGS = [
    dict(name='prolific_study', 
        display_name="Repeated Prisoner's Dilemma Prolific",
        app_sequence=['prisoner'], 
        num_demo_participants=2, 
        completionlink='https://app.prolific.co/submissions/complete?cc=11111111',
    ),
]

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=.01, 
    participation_fee=0.00, 
    doc="",
    # Modern additions:
    use_browser_bots=False,  # Recommended for security
    export_filenames_include_app_name=True  # Better data export
)

LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True


ROOMS = [
dict(
    name='Prolific_1',
    display_name='Prolific_1'
),
dict(
    name='live_demo',
    display_name='Room for Live Demo (No Participant Labels)'
)
]

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

# don't share this with anybody.
SECRET_KEY = '2_1xpevqi65$0e$w4=)@izbb*pu3jo^z)rca1hfsqg@p3gnmah'
