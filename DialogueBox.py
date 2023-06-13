from utils import Button
import settings
import pygame

class DialogueBox:
    def __init__(self, window, message, font):
        self.window = window
        self.message = message
        self.font = font
        self.rect = pygame.Rect(settings.get_x(0.225), settings.get_y(0.35), settings.DIALOGUE_BOX_WIDTH, settings.DIALOGUE_BOX_HEIGHT)
        self.accept_button = Button(self.window, settings.get_x(0.28), settings.get_y(0.45), 'Accept')
        self.reject_button = Button(self.window, settings.get_x(0.52), settings.get_y(0.45), 'Reject')

    def draw(self):
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
