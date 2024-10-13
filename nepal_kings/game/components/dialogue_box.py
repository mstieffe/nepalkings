from utils.utils import Button
from config import settings
import pygame

import textwrap


class DialogueBox:
    def __init__(self, window, message, font, actions=None):
        if actions is None:
            actions = ['ok']
        self.window = window
        self.message = message
        self.font = font
        if actions:
            self.actions = actions
        else:
            self.actions = ['ok']
        #self.line_spacing = settings.SMALL_SPACER_Y  # You can adjust this value

        # Calculate the message lines
        self.lines = textwrap.wrap(self.message, width=(settings.DIALOGUE_BOX_WIDTH - settings.SMALL_SPACER_X) // (2*self.font.size(' ')[0]))
        self.lines_surfaces = [self.font.render(line, True, settings.MSG_TEXT_COLOR) for line in self.lines]

        # Calculate the new box height
        box_height = settings.DIALOGUE_BOX_HEIGHT + (len(self.lines) - 1) * (self.font.get_height() + settings.SMALL_SPACER_Y)

        # Calculate the position of the box to make sure it's in the center
        box_x = settings.CENTER_X - settings.DIALOGUE_BOX_WIDTH / 2
        box_y = settings.CENTER_Y - box_height / 2
        #box_y = (self.window.get_height() - box_height) / 2

        self.rect = pygame.Rect(box_x, box_y, settings.DIALOGUE_BOX_WIDTH, box_height)

        # Adjust the buttons
        button_y = self.rect.y + self.rect.height - 2*settings.SMALL_SPACER_Y - settings.BUTTON_HEIGHT
        #button_y = box_y + box_height / 4 + (len(self.lines)-1) * (self.font.get_height() + settings.SMALL_SPACER_Y)
        #button_names = ['Accept', 'Reject']
        first_button_x = settings.CENTER_X - len(self.actions) * (settings.BUTTON_WIDTH / 2) - (len(self.actions) - 1) * (settings.SMALL_SPACER_X / 2)
        button_x = [first_button_x + n * (settings.BUTTON_WIDTH + settings.SMALL_SPACER_X) for n in range(len(self.actions))]
        self.buttons = [Button(self.window, button_x[i], button_y, self.actions[i]) for i in range(len(self.actions))]
        #self.accept_button = Button(self.window, settings.CENTER_X - settings.BUTTON_WIDTH / 2 - settings.BUTTON_WIDTH, button_y, 'Accept')
        #self.reject_button = Button(self.window, settings.CENTER_X - settings.BUTTON_WIDTH / 2 + settings.BUTTON_WIDTH, button_y, 'Reject')

    def draw(self):
        # Draw Box
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, self.rect)

        # Draw each line of the message
        for i, line_surface in enumerate(self.lines_surfaces):
            line_y = self.rect.y + (i+1) * (self.font.get_height() + settings.SMALL_SPACER_Y)
            line_rect = line_surface.get_rect(center=(self.rect.centerx, line_y))
            self.window.blit(line_surface, line_rect)

        # Draw the buttons
        for button in self.buttons:
            button.draw()
        #self.accept_button.draw()
        #self.reject_button.draw()

    def update(self, events):
        # Update the button colors
        for button in self.buttons:
            button.update()
        #self.accept_button.update_color()
        #self.reject_button.update_color()

        # Handle the button click events
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                for button in self.buttons:
                    if button.collide():
                        return button.text.lower()
                #if self.accept_button.collide():
                #    return 'accept'
                #elif self.reject_button.collide():
                #    return 'reject'
        return None
"""
class DialogueBoxOLD:
    def __init__(self, window, message, font):
        self.window = window
        self.message = message
        self.font = font
        self.rect = pygame.Rect(settings.get_x(0.225), settings.get_y(0.35), settings.DIALOGUE_BOX_WIDTH, settings.DIALOGUE_BOX_HEIGHT)
        self.accept_button = Button(self.window, settings.get_x(0.28), settings.get_y(0.45), 'Accept')
        self.reject_button = Button(self.window, settings.get_x(0.52), settings.get_y(0.45), 'Reject')

    def draw(self):
        # Calculate the width based on the text size
        text_width, text_height = self.font.size(self.message)
        box_width = text_width + settings.SMALL_SPACER_X  # Adding some padding

        # Update the width of the box
        self.rect.width = box_width

        box_x = (self.window.get_width() - box_width) // 2
        box_y = settings.get_y(0.35)
        self.rect.topleft = (box_x, box_y)

        # Draw Box
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, self.rect)

        # Draw the message
        text_obj = self.font.render(self.message, True, settings.BLACK)
        text_rect = text_obj.get_rect(center=(settings.get_x(0.5), settings.get_y(0.4)))
        self.window.blit(text_obj, text_rect)

        # Draw the buttons
        self.accept_button.draw()
        self.reject_button.draw()

    def update(self, events):
        # Update the button colors
        self.accept_button.update_color()
        self.reject_button.update_color()

        # Handle the button click events
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.accept_button.collide():
                    return 'accept'
                elif self.reject_button.collide():
                    return 'reject'
        return None

class InfoBox:
    def __init__(self, window, message, font):
        self.window = window
        self.message = message
        self.font = font
        self.rect = pygame.Rect(settings.get_x(0.225), settings.get_y(0.35), 0, settings.DIALOGUE_BOX_HEIGHT)
        button_x = settings.SCREEN_WIDTH // 2 - settings.BUTTON_WIDTH // 2
        self.ok_button = Button(self.window, button_x, settings.get_y(0.45), 'OK')

    def draw(self):
        # Calculate the width based on the text size
        text_width, text_height = self.font.size(self.message)
        box_width = text_width + settings.SMALL_SPACER_X  # Adding some padding

        # Update the width of the box
        self.rect.width = box_width

        box_x = (self.window.get_width() - box_width) // 2
        box_y = settings.get_y(0.35)
        self.rect.topleft = (box_x, box_y)

        # Draw Box
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, self.rect)

        # Draw the message
        text_obj = self.font.render(self.message, True, settings.BLACK)
        text_rect = text_obj.get_rect(center=(settings.get_x(0.5), settings.get_y(0.4)))
        self.window.blit(text_obj, text_rect)

        # Draw the buttons
        self.ok_button.draw()

    def update(self, events):
        # Update the button colors
        self.ok_button.update_color()

        # Handle the button click events
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.ok_button.collide():
                    return True
        return None
"""

