# Orbit Wars: Core Game Rules & Physics Specification

This document provides the complete, ground-truth gameplay specifications, mechanics, and physics rules for Orbit Wars. It serves as the baseline game design document that both the Python reference engine and the C implementation conform to.

---

## 1. Board Layout and Space Geometry

- Coordinate Space: Continuous 2D space of size 100.0 * 100.0 units. The coordinate origin (0, 0) is located at the top-left corner of the board.
- The Sun: Centered exactly at (50.0, 50.0) with a radius of 10.0 units. 
  - Sun Hazard: Any traveling fleet whose line-segment path intersects the sun's radius is immediately destroyed and removed from the game (all ships lost).
- Rotational Symmetry: The board layout is generated with 4-fold rotational symmetry around the center of the board (50.0, 50.0). Any planet generated at coordinates (x, y) will have its symmetric counterparts generated at:
  - (100.0 - x, y)
  - (x, 100.0 - y)
  - (100.0 - x, 100.0 - y)
  
  This ensures exact starting balance and fair distances regardless of starting slot positions.

---

## 2. Planets and Orbits

Planets are static or orbiting bodies containing defensive ship garrisons and generating reinforcements.

### Planet Attributes
Each planet is represented by the following attributes:
- id: A unique integer identifying the planet.
- owner: Player index (0-3), or -1 for neutral.
- x, y: Float coordinate position in continuous space.
- radius: Computed dynamically from its production capacity:
  $$\text{radius} = 1.0 + \ln(\text{production})$$
- production: An integer from 1 to 5 denoting ship generation capacity per step.
- ships: The current garrison size.
- is_comet: A boolean indicating if the planet is a temporary comet.

### Planet Types
1. Orbiting Planets: Planets generated closer to the sun whose orbital radius plus planet radius is less than 50.0.
   - They orbit the sun at a constant distance (orbital radius) with a fixed angular velocity omega (randomly selected at game initialization from [0.025, 0.05] radians/step).
   - All orbiting planets rotate in the same direction and at the same angular velocity.
2. Static Planets: Planets generated further out (orbital radius plus radius >= 50.0). These planets remain at fixed coordinates for the duration of the episode.

> [!NOTE]
> The map generator places between 20 and 40 planets (5 to 10 symmetric groups of 4). At least 1 group is guaranteed to orbit, and at least 3 groups are guaranteed to remain static.

### Home Planets
At initialization, one symmetric group of planets is selected as players' starting home bases. 
- 2-Player Games (1v1): Players start on diagonally opposite planets (e.g., Quadrant 1 and Quadrant 4).
- 4-Player Games (4v4): Each player starts on one planet in the 4-fold symmetric home group.
- Starting Garrison: Home planets initialize with exactly 10 ships. Neutral planets initialize with a randomized garrison between 5 and 99 ships (logarithmically skewed toward smaller values).

---

## 3. Fleets and Travel Physics

Players launch fleets to capture other planets or reinforce their own.

### Fleet Attributes
Fleets travel in straight lines across the continuous board space and are represented by:
- id: A unique integer identifying the fleet.
- owner: The player index (0-3) who owns the traveling fleet.
- x, y: Float coordinates of the fleet's current position.
- angle: Heading in radians (0.0 is rightward, pi/2 is downward).
- from_planet_id: The ID of the planet the fleet was launched from.
- ships: The integer number of ships contained in the fleet.
- speed: Float velocity of the fleet (calculated from size).

### Fleet Launch Mechanics
Fleets are spawned by player launch actions:
1. Sufficient Garrison: A player can only launch from a planet they currently own, and cannot launch more ships than the planet's current garrison minus one (at least 1 ship must remain on the planet).
2. Spawn Position: To prevent immediate self-collision, a fleet does not spawn at the planet's center. Instead, it spawns just outside the planet's radius in the direction of the launch angle:
   $$\text{spawn\_x} = \text{planet\_x} + (\text{planet\_radius} + 0.1) \times \cos(\theta)$$
   $$\text{spawn\_y} = \text{planet\_y} + (\text{planet\_radius} + 0.1) \times \sin(\theta)$$

### Non-Linear Speed Scaling
Fleet speed is proportional to the logarithm of the number of ships traveling in it:
$$\text{speed} = \min\left(1.0 + (\text{max\_speed} - 1.0) \times \left(\frac{\ln(\text{ships})}{\ln(1000)}\right)^{1.5}, \text{max\_speed}\right)$$
- max_speed is default to 6.0 units/turn.
- A fleet with 1 ship travels at 1.0 unit/turn.
- A fleet with 500 ships travels at approx 5.0 units/turn.
- A fleet with 1000 or more ships reaches the maximum speed of 6.0 units/turn.

### Continuous swept-pair collision checking
Because objects move at high velocities, basic discrete step checks would allow fleets to "tunnel" through planets or the sun. The game uses continuous swept-pair intersection tests:
- A fleet path from (x0, y0) to (x1, y1) is treated as a continuous line segment.
- If this line segment passes within the radius R of the Sun or any active Planet during the step, a collision is detected.
- If a fleet collides with the sun, it is destroyed.
- If a fleet collides with a planet, it is halted at the collision point and queued for combat at the end of the turn.

---

## 4. Comets

Comets are temporary celestial bodies that fly through the solar system on highly elliptical, gravity-assisted paths.

- Spawning: One group of 4 symmetric comets spawns at step 50, 150, 250, 350, and 450.
- Radius: 1.0 (fixed).
- Production: 1 ship/turn when owned.
- Starting Garrison: A random ship count between 5 and 99, shared symmetrically across all 4 comets in the group.
- Speed: Path advancement is fixed at 4.0 units/step.
- Comet Paths: Calculated at initialization via gravity simulation, resulting in 100 steps of elliptical coordinates.
- Expiration: Once a comet reaches the end of its 100-step path (or goes out of bounds), it is deleted along with any ships garrisoned on it. Expiration occurs before fleet launches, so players cannot launch fleets from a comet on the turn it expires.

---

## 5. Turn Phase Execution Order

To avoid execution order bugs, each game step must run its logic in the exact chronological sequence:

1. Comet Expiration: Check and remove comets that have reached their path limits.
2. Comet Spawning: Spawn new comets if the step index matches spawn points.
3. Fleet Launch: Process actions from all players, decrement planet garrisons, and spawn fleets.
4. Production: All owned planets and comets increase their garrisons by their production rate.
5. Fleet Movement: Advance fleets along their heading vector. Perform continuous swept-pair collision checks against the Sun and Planets. Queue colliding fleets for combat.
6. Planet & Comet Movement: Rotate orbiting planets around the sun. Advance comets along their path arrays. Any active fleet swept by a moving body is queued for combat.
7. Combat Resolution: Resolve queued combat at planets.
8. Episode Termination Check: Verify if step limit is reached or players are eliminated.

---

## 6. Combat Resolution Logic

Combat occurs when one or more fleets arrive at a planet on the same turn.

1. Group by Owner: All arriving fleets are grouped by their owner ID. The number of ships for each owner is summed.
2. Attacker Battle: The largest attacking force battles the second-largest attacking force:
   - If the largest force exceeds the second-largest, the largest force survives with a size equal to the difference:
     $$\text{surviving\_attacker\_ships} = \text{largest\_attacker\_ships} - \text{second\_largest\_attacker\_ships}$$
   - If there is a tie for the largest force, all attacking fleets are destroyed (no attacker survives).
3. Planet Interaction:
   - No Attacker Survives: The planet's owner and garrison remain unchanged.
   - Attacker Belongs to Planet Owner: The surviving attacker ships are added directly to the planet's garrison.
   - Attacker Belongs to Opponent: The surviving attacker ships fight the planet's garrison:
     - If attacker ships exceed the garrison:
       $$\text{new\_garrison} = \text{attacker\_ships} - \text{garrison\_ships}$$
       The planet's ownership changes to the attacker's owner.
     - If garrison ships exceed the attacker:
       $$\text{new\_garrison} = \text{garrison\_ships} - \text{attacker\_ships}$$
       Ownership remains unchanged.
     - If there is an exact tie, the planet becomes neutral (owner = -1) with 0 ships.

---

## 7. Scoring and Termination

- Episode Length: Exactly 500 steps.
- Elimination: An agent is eliminated if they own 0 planets and 0 active fleets. If only one player (or zero players) remains, the game ends immediately.
- Final Score: At termination, each player's score is computed:
  $$\text{Score}_p = \sum \text{ships on owned planets} + \sum \text{ships in owned fleets}$$
- Rewards: Terminal rewards are sparse:
  - Winner: 1.0
  - Tie/Draw: 0.5
  - Loser: 0.0
  - All intermediate (non-terminal) steps return a reward of 0.0.
