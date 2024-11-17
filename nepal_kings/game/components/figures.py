import pygame
from config import settings


class Figure():
    def __init__(self, name, suit, icon_img, icon_darkwhite_img, visible_img, hidden_img, key_cards, number_card=None, upgrade_card=None, altar_card=None, description='', field=None):

        self.name = name
        self.description = description

        self.field = field
        self.suit = suit

        self.key_cards = key_cards

        self.number_card = number_card

        self.upgrade_card = upgrade_card

        self.altar_card = altar_card

        self.icon_img = icon_img
        self.icon_darkwhite_img = icon_darkwhite_img
        self.visible_img = visible_img
        self.hidden_img = hidden_img

        self.upgrade_to = []

        self.cards = self.key_cards[:]
        if self.number_card:
            self.cards.append(self.number_card)
        if self.upgrade_card:
            self.cards.append(self.upgrade_card)
        if self.altar_card:
            self.cards.append(self.altar_card)

    def draw(self, window, x, y, visible=True):
        if visible:
            img = self.visible_img
        else:
            img = self.hidden_img
        window.blit(img, (x, y))

    #def draw_icon(self, window, x, y):
    #    window.blit(self.icon_img, (x, y))

class FigureManager:
    def __init__(self):

        self.figures = []
        self.figures_by_field = {'all': [],
                                 'village': [],
                                 'military': [],
                                 'castle': []}
        self.figures_by_suit = {'Hearts': [],
                                 'Diamonds': [],
                                 'Spades': [],
                                 'Clubs': []}

        self.figures_by_name = {}

        self.figures_by_number_card = {}



        # Farm
        self.initialize_main_figures(
            name='Farm',
            description=['Farm II description. Food production like farm 1 but stronger etc',
                         'Farm II description. Food production like farm 1 but stronger etc',
                         'Farm II description. Food production like farm 1 but stronger etc',
                         'Farm II description. Food production like farm 1 but stronger etc'],
            img='farm',
            key_ranks=['J'],
            upgrade_rank='Q',
            field='village')

        # Temple1
        self.initialize_main_figures(
            name='Temple',
            description=['Farm II description. Food production like farm 1 but stronger etc',
                         'Farm II description. Food production like farm 1 but stronger etc',
                         'Farm II description. Food production like farm 1 but stronger etc',
                         'Farm II description. Food production like farm 1 but stronger etc'],
            img='temple',
            key_ranks=['Q', 'Q'],
            number_ranks=[None],
            upgrade_rank='7',
            field='village')

        # Barrack1
        self.initialize_main_figures(
            name='Barracks',
            img='barrack',
            key_ranks=['A'],
            upgrade_rank='7',
            suits=['Hearts', 'Diamonds'],
            description=['Bacrrack I description. Food production etc',
                         'Bacrrack I description. Food production etc'],
            field='military')

        # Tower
        self.initialize_main_figures(
            name='Tower',
            img='tower',
            key_ranks=['A'],
            upgrade_rank='7',
            suits = ['Spades', 'Clubs'],
            description=['Bacrrack I description. Food production etc',
                         'Bacrrack I description. Food production etc'],
            field='military')

        # Catapult
        self.initialize_side_figures(
            name='Archery',
            description='Catapult description. Food production etc',
            img='catapult',
            key_ranks=['J', '3']
        )

        # Wall
        self.initialize_side_figures(
            name='Wall',
            description='Wall description. Food production etc',
            img='wall',
            key_ranks=['4', '5', '6'],
            suits=['Spades', 'Clubs']
        )

        # Cavalry
        self.initialize_side_figures(
            name='Cavalry',
            description='Cavalry description. Food production etc',
            img='cavalry',
            key_ranks=['4', '5', '6'],
            suits=['Hearts', 'Diamonds']
        )

    def initialize_side_figures(self, name, description, img, key_ranks, suits=settings.SUITS, field='military'):

        icon_img = pygame.image.load(settings.FIGURE_ICON_IMG_PATH+img + '.png')
        icon_darkwhite_img = pygame.image.load(settings.FIGURE_ICON_DARKWHITE_IMG_PATH+img + '.png')

        #icon_img = pygame.transform.scale(icon_img, (settings.FIGURE_ICON_BIG_WIDTH, settings.FIGURE_ICON_BIG_HEIGHT))
        visible_img = pygame.image.load(settings.FIGURE_VISIBLE_IMG_PATH+img + '.png')
        #visible_img = pygame.transform.scale(visible_img, (settings.FIGURE_WIDTH, settings.FIGURE_HEIGHT))
        hidden_img = pygame.image.load(settings.FIGURE_HIDDEN_IMG_PATH+img + '.png')
        #hidden_img = pygame.transform.scale(hidden_img, (settings.FIGURE_WIDTH, settings.FIGURE_HEIGHT))

        for suit in suits:
            key_cards = [(suit, rank) for rank in key_ranks]
            self.add_figure(Figure(name=name,
                                   suit=suit,
                                   icon_img=icon_img,
                                   icon_darkwhite_img=icon_darkwhite_img,
                                   visible_img=visible_img,
                                   hidden_img=hidden_img,
                                   key_cards=key_cards,
                                   number_card=None,
                                   upgrade_card=None,
                                   altar_card=None,
                                   description=description,
                                   field=field
                                   ))

    def initialize_main_figures(self, name, description, img, key_ranks, upgrade_rank=None, number_ranks=settings.NUMBER_CARDS, suits=settings.SUITS, field='village'):

        icon_img1 = pygame.image.load(settings.FIGURE_ICON_IMG_PATH+img + '1.png')
        icon_darkwhite_img1 = pygame.image.load(settings.FIGURE_ICON_DARKWHITE_IMG_PATH+img + '1.png')

        #icon_img1 = pygame.transform.scale(icon_img1, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        icon_img2 = pygame.image.load(settings.FIGURE_ICON_IMG_PATH + img + '2.png')
        icon_darkwhite_img2 = pygame.image.load(settings.FIGURE_ICON_DARKWHITE_IMG_PATH + img + '2.png')

        #icon_img2 = pygame.transform.scale(icon_img2, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        visible_img1 = pygame.image.load(settings.FIGURE_VISIBLE_IMG_PATH+img + '1.png')
        #visible_img1 = pygame.transform.scale(visible_img1, (settings.FIGURE_WIDTH, settings.FIGURE_HEIGHT))
        visible_img2 = pygame.image.load(settings.FIGURE_VISIBLE_IMG_PATH+img + '2.png')
        #visible_img2 = pygame.transform.scale(visible_img2, (settings.FIGURE_WIDTH, settings.FIGURE_HEIGHT))
        if field == 'village':
            hidden_img = pygame.image.load(settings.FIGURE_HIDDEN_IMG_PATH + 'village.png')
        else:
            hidden_img = pygame.image.load(settings.FIGURE_HIDDEN_IMG_PATH+img + '.png')
        hidden_img = pygame.transform.scale(hidden_img, (settings.FIGURE_WIDTH, settings.FIGURE_HEIGHT))

        for suit in suits:
            key_cards = [(suit, rank) for rank in key_ranks]
            for number_rank in number_ranks:
                #altar_cards = [None, (suit, '2')] if field == 'village' else [None]
                number_card = (suit, number_rank) if number_rank else None
                upgrade_card = (suit, upgrade_rank)
                #for altar_card in altar_cards:
                #print(name, suit, key_cards, number_card, upgrade_card)

                self.add_figure(Figure(name=name + ' I',
                                       suit=suit,
                                       icon_img=icon_img1,
                                       icon_darkwhite_img=icon_darkwhite_img1,
                                       visible_img=visible_img1,
                                       hidden_img=hidden_img,
                                       key_cards=key_cards,
                                       number_card=number_card,
                                       upgrade_card=None,
                                       altar_card=None,
                                       description=description[0],
                                       field=field
                                       ))
                self.add_figure(Figure(name=name + ' II',
                                       suit=suit,
                                       icon_img=icon_img2,
                                       icon_darkwhite_img=icon_darkwhite_img2,
                                       visible_img=visible_img2,
                                       hidden_img=hidden_img,
                                       key_cards=key_cards,
                                       number_card=number_card,
                                       upgrade_card=upgrade_card,
                                       altar_card=None,
                                       description=description[1],
                                       field=field
                                       ))
                self.figures[-2].upgrade_to.append(self.figures[-1])
                if field == 'village':
                    self.add_figure(Figure(name=name + ' I with Altar',
                                           suit=suit,
                                           icon_img=icon_img1,
                                           icon_darkwhite_img=icon_darkwhite_img1,
                                           visible_img=visible_img1,
                                           hidden_img=hidden_img,
                                           key_cards=key_cards,
                                           number_card=number_card,
                                           upgrade_card=None,
                                           altar_card=(suit, '2'),
                                           description=description[2],
                                           field=field
                                           ))
                    self.add_figure(Figure(name=name + ' II with Altar',
                                           suit=suit,
                                           icon_img=icon_img2,
                                           icon_darkwhite_img=icon_darkwhite_img2,
                                           visible_img=visible_img2,
                                           hidden_img=hidden_img,
                                           key_cards=key_cards,
                                           number_card=number_card,
                                           upgrade_card=upgrade_card,
                                           altar_card=(suit, '2'),
                                           description=description[3],
                                           field=field
                                           ))
                    #self.figures[-4].upgrade_to.append(self.figures[-3])

                    self.figures[-4].upgrade_to.append(self.figures[-2])
                    self.figures[-2].upgrade_to.append(self.figures[-1])
                    self.figures[-3].upgrade_to.append(self.figures[-1])

    def add_figure(self, figure):
        self.figures.append(figure)
        self.figures_by_field[figure.field].append(figure)
        self.figures_by_suit[figure.suit].append(figure)

        if figure.name not in self.figures_by_name:
            self.figures_by_name[figure.name] = [figure]
        else:
            self.figures_by_name[figure.name].append(figure)

        if figure.number_card not in self.figures_by_number_card:
            self.figures_by_number_card[figure.number_card] = [figure]
        else:
            self.figures_by_number_card[figure.number_card].append(figure)

    def match_figure(self, cards):
        # Convert input list of cards and figure cards to sets for easier comparison
        card_set = set(cards)
        for figure in self.figures:
            if set(figure.cards) == card_set:
                return figure  # If a match is found, return the matching figure
        return None  # If no match is found, return None
