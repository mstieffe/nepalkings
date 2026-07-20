# Gameplay Guide

This guide explains the two main Nepal Kings experiences and the shared card
language. The in-game **Guide** is authoritative for the exact rules and card
effects included with the client you are playing.

## The core loop

1. Complete the First Journey and reveal the starter Collection.
2. Prepare a Conquest force and attack an AI-held land.
3. Win territory, collect its production, and maintain its defence.
4. Open boosters and improve future attack and defence configurations.
5. Play Duels against the AI or other rulers for longer head-to-head matches.

Conquest does not require another human player. Multiplayer extends the same
collection and kingdom systems but is not required to begin progressing.

## Conquest

Conquest is a prepared battle for one land on the persistent kingdom map.

### Before battle

- Choose a land and inspect its tier, suit bonus, production, and defender.
- Build figures and tactics from cards in your Collection.
- Cards committed to a configuration remain locked while that configuration
  uses them.
- AI-held lands receive deterministic tier-appropriate defences. Player-owned
  lands use the defence saved by their ruler.

### Battle

The attacker and defender bring their prepared forces into a focused battle.
Figures, modifiers, spells, and tactics determine which side wins. Information
that is meant to remain hidden is revealed only as the battle progresses.

### After battle

- An attacker victory transfers the land and converts the successful attack
  into its initial defence.
- The new owner can later revise the defence using available Collection cards.
- A defender victory preserves ownership.
- Battle results, card locks, rewards, and kingdom connectivity are persisted
  by the server before the client shows the finished result.

## Duels

Duels are longer head-to-head matches against the AI or another player. Both
players draw from a shared deck and build a field over multiple rounds.

### Start and roles

- One player is the attacker and one is the defender.
- A deck cut establishes the Ur-King and opening role conditions.
- Each player can hold up to 12 main hand cards.
- The first round refills toward 12; later rounds normally refill by a smaller
  amount according to the current game state.

### Build phase

The regular build sequence is followed by an attacker advance and a defender
reaction. During eligible turns a player can exchange cards, use an action,
and place, collect, or modify figures.

- **Passive build:** passive actions only; advancing is unavailable.
- **Active build:** active actions and advancing are available.

Some actions can force or reshape the next battle. Always use the card text
and in-game Guide for exact legality and counter timing.

### Battle phase

1. Eligible fighting figures and battle resources are selected.
2. The figures are revealed and their power, field, suit, and support effects
   are calculated.
3. Players resolve up to three tactical battle rounds.
4. The defeated figure and active modifiers determine the awarded points.

Special battle conditions include Direct Battle, Peasant War, King's Battle,
and Blitzkrieg. Their exact figure restrictions and targeting rules are shown
in the in-game Guide when relevant.

### Winning

The first player to reach the selected point target wins. Quick (7), Standard
(21), and Epic (35) are convenient presets; custom point targets are also
supported. Checkmate effects can end a Duel under their documented conditions.

## Suits and support

Suit advantage follows a cycle:

```text
Hearts → Clubs → Diamonds → Spades → Hearts
```

Matching-suit figures can provide support where the figure and phase rules
allow it. A donor can contribute only as permitted by the current effect; the
server remains the final legality authority.

## Card values

| Card | Base value |
|---|---:|
| Jack | 1 |
| Queen | 2 |
| Ace | 3 |
| King | 4 |
| Ur-King | 5; special figure value applies when fighting |
| Number card | Printed value |

The same physical rank can serve different purposes depending on whether it is
used in a figure recipe, spell, modifier, tactic, or battle.

## Card and object vocabulary

- **Collection card:** a persistent card copy owned by an account.
- **Figure:** a built unit with a field, colour, suit, recipe, and abilities.
- **Action or spell:** an effect that changes setup, field state, or battle.
- **Tactic or battle card:** a prepared or drawn battle resource.
- **Configuration:** the persisted attack or defence assembled for Conquest.
- **Land:** one tile on the shared kingdom map.
- **Kingdom:** connected player-owned lands and their progression state.

## Online play and safety

Duels can continue asynchronously. The server stores the authoritative match
state, and the client refreshes it when a player returns. Use **Settings →
Safety** to block or report another player. See [Support](../SUPPORT.md) for
account help, appeals, and security-reporting boundaries.
