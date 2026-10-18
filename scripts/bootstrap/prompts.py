"""Small terminal prompts; secrets never fall back to visible input."""
import getpass
import warnings


def ask(label, default=None, validate=None, secret=False):
    while True:
        suffix = f' [{default}]' if default is not None else ''
        if secret:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                try:
                    value = getpass.getpass(f'{label}: ').strip()
                except getpass.GetPassWarning as exc:
                    raise RuntimeError('A terminal is required for hidden database input.') from exc
        else:
            value = input(f'{label}{suffix}: ').strip()
        value = value or default
        if not value:
            print('Please enter a value.')
            continue
        try:
            return validate(value) if validate else value
        except ValueError as exc:
            print(str(exc))


def confirm(label, default=False):
    while True:
        value = input(f'{label} [{"Y/n" if default else "y/N"}]: ').strip().lower()
        if not value:
            return default
        if value in ('yes', 'y'):
            return True
        if value in ('no', 'n'):
            return False
        print('Please answer yes or no.')


def choose(label, options):
    print(label)
    for i, option in enumerate(options, 1):
        print(f'  {i}. {option}')
    while True:
        value = input('Choose a number [1]: ').strip() or '1'
        if value.isdigit() and 1 <= int(value) <= len(options):
            return int(value) - 1
        print(f'Choose a number from 1 to {len(options)}.')
