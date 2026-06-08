"""Team codes and display names derived from flag sets in app/static/flags/."""

# Display names for all codes appearing in the repository flag sets.
TEAM_NAMES = {
    'ALB': 'Albania',
    'ALG': 'Algeria',
    'ARG': 'Argentina',
    'AUS': 'Australia',
    'AUT': 'Austria',
    'BEL': 'Belgium',
    'BIH': 'Bosnia and Herzegovina',
    'BLR': 'Belarus',
    'BRA': 'Brazil',
    'CAN': 'Canada',
    'CIV': 'Ivory Coast',
    'CMR': 'Cameroon',
    'COD': 'DR Congo',
    'COL': 'Colombia',
    'CPV': 'Cape Verde',
    'CRC': 'Costa Rica',
    'CRO': 'Croatia',
    'CUW': 'Curaçao',
    'CZE': 'Czechia',
    'DEN': 'Denmark',
    'ECU': 'Ecuador',
    'EGY': 'Egypt',
    'ENG': 'England',
    'ESP': 'Spain',
    'FIN': 'Finland',
    'FRA': 'France',
    'GBR': 'Great Britain',
    'GEO': 'Georgia',
    'GER': 'Germany',
    'GHA': 'Ghana',
    'HAI': 'Haiti',
    'HUN': 'Hungary',
    'IRN': 'Iran',
    'IRQ': 'Iraq',
    'ITA': 'Italy',
    'JOR': 'Jordan',
    'JPN': 'Japan',
    'KAZ': 'Kazakhstan',
    'KOR': 'South Korea',
    'KSA': 'Saudi Arabia',
    'LAT': 'Latvia',
    'MAR': 'Morocco',
    'MEX': 'Mexico',
    'MKD': 'North Macedonia',
    'NED': 'Netherlands',
    'NOR': 'Norway',
    'NZL': 'New Zealand',
    'PAN': 'Panama',
    'PAR': 'Paraguay',
    'POL': 'Poland',
    'POR': 'Portugal',
    'QAT': 'Qatar',
    'ROU': 'Romania',
    'RSA': 'South Africa',
    'RUS': 'Russia',
    'SCO': 'Scotland',
    'SEN': 'Senegal',
    'SLO': 'Slovenia',
    'SRB': 'Serbia',
    'SUI': 'Switzerland',
    'SVK': 'Slovakia',
    'SVN': 'Slovenia',
    'SWE': 'Sweden',
    'TUN': 'Tunisia',
    'TUR': 'Turkey',
    'UKR': 'Ukraine',
    'URU': 'Uruguay',
    'USA': 'United States',
    'UZB': 'Uzbekistan',
    'WAL': 'Wales',
}

# set1 + set_footballs + root-level flags/ (World Cup / Euro tournaments).
FOOTBALL_CODES = {
    'ALB', 'ALG', 'ARG', 'AUS', 'AUT', 'BEL', 'BIH', 'BRA', 'CAN', 'CIV', 'CMR',
    'COD', 'COL', 'CPV', 'CRC', 'CRO', 'CUW', 'CZE', 'DEN', 'ECU', 'EGY', 'ENG',
    'ESP', 'FIN', 'FRA', 'GEO', 'GER', 'GHA', 'HAI', 'HUN', 'IRN', 'IRQ', 'ITA',
    'JOR', 'JPN', 'KOR', 'KSA', 'MAR', 'MKD', 'MEX', 'NED', 'NOR', 'NZL', 'PAN',
    'PAR', 'POL', 'POR', 'QAT', 'ROU', 'RSA', 'RUS', 'SCO', 'SEN', 'SRB', 'SUI',
    'SVK', 'SVN', 'SWE', 'TUN', 'TUR', 'UKR', 'URU', 'USA', 'UZB', 'WAL',
}

# set2 + set3 + set4 + set5 (ice hockey tournaments).
HOCKEY_CODES = {
    'AUT', 'BLR', 'CAN', 'CZE', 'DEN', 'FIN', 'FRA', 'GBR', 'GER', 'HUN', 'ITA',
    'KAZ', 'LAT', 'NOR', 'POL', 'RUS', 'SLO', 'SUI', 'SVK', 'SWE', 'USA',
}

SPORT_CODES = {
    'football': FOOTBALL_CODES,
    'hockey': HOCKEY_CODES,
}


def iter_team_rows():
    """Yield (sport, code, name) tuples for database seeding."""
    for sport, codes in sorted(SPORT_CODES.items()):
        for code in sorted(codes):
            name = TEAM_NAMES.get(code)
            if name is None:
                raise ValueError(f'Missing display name for team code {code!r}')
            yield sport, code, name
