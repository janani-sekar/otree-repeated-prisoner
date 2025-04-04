from os import environ

SESSION_CONFIGS = [
    dict(
        name='prisoner',
        display_name="Repeated Prisoner's Dilemma",
        app_sequence=['prisoner'],  # Use ONLY apps that exist
        num_demo_participants=2,
    )
]

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00, 
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
    name='prolific_study',
    display_name='prolific_study',
    participant_label_file='_rooms/Prolific_1.txt',
),
dict(
    name='live_demo',
    display_name='Room for Live Demo (No Participant Labels)',
)
]

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

# don't share this with anybody.
SECRET_KEY = '2_1xpevqi65$0e$w4=)@izbb*pu3jo^z)rca1hfsqg@p3gnmah'
