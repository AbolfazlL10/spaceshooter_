
import json
import math
import os
import random
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.graphics import (
    Color, Ellipse, Line, Rectangle, RoundedRectangle,
    PushMatrix, PopMatrix, Translate,
)
from kivy.metrics import dp
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.widget import Widget

# ============================================================
# SPACE SHOOTER 2.0 - KIVY MOBILE EDITION (ENHANCED FX BUILD)
# ============================================================

SAVE_NAME = "save_v8.json"


def get_save_path():
    # On Android the app folder may be read-only, so use the app's own data dir.
    try:
        app = App.get_running_app()
        base = app.user_data_dir if app else "."
    except Exception:
        base = "."
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, SAVE_NAME)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def load_save():
    default = {
        "coins": 0,
        "high_score": 0,
        "weapon_levels": [1, 1, 1],
        "player_level": 1,
        "xp": 0,
        "unlocked_weapon": 0,
        "best_stage": 1,
    }
    try:
        with open(get_save_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        default.update(data)
    except Exception:
        pass
    return default


def save_game(data):
    try:
        with open(get_save_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


def poly_points(cx, cy, r, sides, rotation=0.0):
    """Return a closed point list for a regular polygon (for Line/Mesh)."""
    pts = []
    for i in range(sides):
        a = rotation + math.tau * i / sides
        pts.append(cx + math.cos(a) * r)
        pts.append(cy + math.sin(a) * r)
    pts.append(pts[0])
    pts.append(pts[1])
    return pts


def star_points(cx, cy, r_out, r_in, spikes, rotation=0.0):
    """Return a closed point list for a 5(ish)-pointed star shape."""
    pts = []
    for i in range(spikes * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rotation + math.pi * i / spikes
        pts.append(cx + math.cos(a) * r)
        pts.append(cy + math.sin(a) * r)
    pts.append(pts[0])
    pts.append(pts[1])
    return pts


def ease_out_cubic(t):
    t = clamp(t, 0, 1)
    return 1 - (1 - t) ** 3


class Particle:
    def __init__(self, x, y, color, power=1.0, gravity=0.0, size_mult=1.0):
        a = random.random() * math.tau
        speed = random.uniform(40, 180) * power
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(a) * speed, math.sin(a) * speed
        self.life = random.uniform(.25, .75) * (0.7 + 0.6 * power)
        self.max_life = self.life
        self.size = random.uniform(2, 6) * power * size_mult
        self.color = color
        self.gravity = gravity

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy -= self.gravity * dt
        self.vx *= .97
        self.vy *= .97
        self.life -= dt
        return self.life > 0


class DamageText:
    """Floating text (damage numbers, combo popups, level-up banners)."""

    def __init__(self, x, y, text, color=(1, 1, 1), font_size=20, vy=62, life=0.85, bold=True):
        self.x = x
        self.y = y
        self.vy = vy
        self.vx = random.uniform(-8, 8)
        self.life = life
        self.max_life = life
        try:
            lbl = CoreLabel(text=text, font_size=font_size, bold=bold,
                             color=[color[0], color[1], color[2], 1])
            lbl.refresh()
            self.texture = lbl.texture
            self.size = self.texture.size
        except Exception:
            self.texture = None
            self.size = (0, 0)

    def update(self, dt):
        self.y += self.vy * dt
        self.x += self.vx * dt
        self.vy *= 0.94
        self.life -= dt
        return self.life > 0


class Shockwave:
    def __init__(self, x, y, color, max_radius=90, life=0.45, width=3.2):
        self.x, self.y = x, y
        self.color = color
        self.max_radius = max_radius
        self.life = life
        self.max_life = life
        self.width = width

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    @property
    def radius(self):
        t = 1 - (self.life / self.max_life)
        return self.max_radius * ease_out_cubic(t)


class Bullet:
    def __init__(self, x, y, vx, vy, damage, radius=5, enemy=False, color=(1, .8, .2)):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.damage = damage
        self.radius = radius
        self.enemy = enemy
        self.life = 3.0
        self.color = color

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0


class Enemy:
    TYPES = {
        "scout":  dict(hp=28, speed=135, size=20, reward=6, xp=5,
                       color=(.95, .25, .3), glow=(1, .35, .35), sides=3),
        "tank":   dict(hp=95, speed=62, size=31, reward=15, xp=15,
                       color=(.62, .28, .92), glow=(.75, .4, 1), sides=6),
        "shooter":dict(hp=50, speed=82, size=24, reward=12, xp=11,
                       color=(1, .5, .18), glow=(1, .7, .3), sides=4),
        "elite":  dict(hp=170, speed=78, size=34, reward=28, xp=25,
                       color=(.15, .85, 1), glow=(.5, .95, 1), sides=5),
    }

    def __init__(self, kind, x, y, stage):
        p = self.TYPES[kind]
        self.kind = kind
        self.x, self.y = x, y
        self.max_hp = p["hp"] * (1 + (stage - 1) * .13)
        self.hp = self.max_hp
        self.speed = p["speed"] * (1 + (stage - 1) * .015)
        self.size = p["size"]
        self.reward = int(p["reward"] * (1 + stage * .05))
        self.xp = p["xp"]
        self.color = p["color"]
        self.glow = p["glow"]
        self.sides = p["sides"]
        self.phase = random.random() * math.tau
        self.shoot_timer = random.uniform(1.0, 2.5)
        self.flash = 0
        self.rot = random.random() * math.tau
        self.spin = random.choice([-1, 1]) * random.uniform(0.6, 1.6)

    def update(self, dt, game):
        dx = game.player_x - self.x
        dy = game.player_y - self.y
        d = max(.001, math.hypot(dx, dy))
        self.rot += self.spin * dt

        if self.kind == "scout":
            self.x += dx / d * self.speed * dt
            self.y += dy / d * self.speed * dt

        elif self.kind == "tank":
            self.x += dx / d * self.speed * dt
            self.y += dy / d * self.speed * dt

        elif self.kind == "shooter":
            # Keep distance and strafe.
            desired = 270
            direction = -1 if d < desired else 1
            self.x += dx / d * self.speed * direction * dt
            self.y += dy / d * self.speed * direction * dt
            self.phase += dt * 2
            self.x += math.cos(self.phase) * 25 * dt
            self.y += math.sin(self.phase) * 25 * dt

            self.shoot_timer -= dt
            if self.shoot_timer <= 0:
                self.shoot_timer = random.uniform(1.2, 2.3)
                speed = 260 + game.stage * 8
                game.enemy_bullets.append(
                    Bullet(self.x, self.y, dx / d * speed, dy / d * speed,
                           9 + game.stage * 1.5, 5, True, color=(1, .3, .4))
                )

        else:  # elite
            self.phase += dt * 1.5
            self.x += dx / d * self.speed * dt
            self.y += dy / d * self.speed * dt
            self.x += math.sin(self.phase) * 40 * dt

        self.flash = max(0, self.flash - dt)


class Boss:
    def __init__(self, stage, x, y):
        self.stage = stage
        self.x, self.y = x, y
        self.size = 65
        self.max_hp = 900 + stage * 250
        self.hp = self.max_hp
        self.speed = 45 + stage * 2
        self.shoot_timer = 1.0
        self.special_timer = 4.0
        self.phase = 0
        self.flash = 0
        self.rot = 0

    def update(self, dt, game):
        self.phase += dt
        self.rot += dt * 0.8
        self.flash = max(0, self.flash - dt)

        target_x = game.player_x
        target_y = max(game.player_y + 120, game.height * .72)
        dx = target_x - self.x
        dy = target_y - self.y
        d = max(.001, math.hypot(dx, dy))
        self.x += dx / d * self.speed * dt
        self.y += dy / d * self.speed * dt

        self.shoot_timer -= dt
        if self.shoot_timer <= 0:
            self.shoot_timer = max(.35, 1.25 - self.stage * .035)
            angle = math.atan2(game.player_y - self.y, game.player_x - self.x)
            for off in (-.22, 0, .22):
                a = angle + off
                speed = 300 + self.stage * 10
                game.enemy_bullets.append(
                    Bullet(self.x, self.y, math.cos(a) * speed,
                           math.sin(a) * speed, 15 + self.stage * 2, 7, True,
                           color=(1, .15, .45))
                )

        self.special_timer -= dt
        if self.special_timer <= 0:
            self.special_timer = 5.5
            game.trigger_shake(6, 0.25)
            # Radial attack
            for i in range(12):
                a = math.tau * i / 12
                speed = 180 + self.stage * 6
                game.enemy_bullets.append(
                    Bullet(self.x, self.y, math.cos(a) * speed,
                           math.sin(a) * speed, 12 + self.stage, 6, True,
                           color=(1, .35, .1))
                )


class GameWorld(Widget):
    score = NumericProperty(0)
    coins = NumericProperty(0)
    stage = NumericProperty(1)
    player_level = NumericProperty(1)

    WEAPON_COLORS = [(.3, .95, 1), (1, .55, .15), (1, .25, .85)]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.save = load_save()
        self.score = 0
        self.coins = self.save.get("coins", 0)
        self.high_score = self.save.get("high_score", 0)
        self.weapon_levels = list(self.save.get("weapon_levels", [1, 1, 1]))
        self.player_level = self.save.get("player_level", 1)
        self.xp = self.save.get("xp", 0)
        self.weapon = 0

        self.player_x = 0
        self.player_y = 0
        self.player_hp = 100
        self.player_max_hp = 100
        self.shield = 50
        self.max_shield = 50
        self.fire_timer = 0
        self.invincible = 0
        self.combo = 0
        self.combo_timer = 0

        self.enemies = []
        self.bullets = []
        self.enemy_bullets = []
        self.particles = []
        self.items = []
        self.damage_texts = []
        self.shockwaves = []
        self.boss = None

        self.running = False
        self.paused = False
        self.game_over = False
        self.wave = 0
        self.wave_target = 8
        self.spawn_timer = 0
        self.touch_id = None
        self.joy_start = None
        self.joy_pos = None
        self.fire_touch = None
        self.last_time = time.monotonic()

        # --- visual FX state ---
        self.time = 0.0
        self.shake_time = 0.0
        self.shake_mag = 0.0
        self.shake_total = 0.0001
        self.muzzle_flash = 0.0
        self.flash_color = (1, 1, 1)
        self.flash_time = 0.0
        self.flash_total = 0.0001
        self.stars = []
        self.nebula = []
        self._gen_nebula()

        self.bind(size=self._resize)
        Clock.schedule_interval(self.tick, 1 / 60)

    # ---------------------------------------------------------------
    # FX helpers
    # ---------------------------------------------------------------
    def _gen_nebula(self):
        self.nebula = []
        palette = [(.35, .12, .55), (.06, .28, .5), (.5, .08, .3), (.1, .4, .35)]
        for _ in range(5):
            self.nebula.append({
                "rx": random.uniform(.1, .9),
                "ry": random.uniform(.1, .9),
                "r": random.uniform(90, 190),
                "color": random.choice(palette),
                "phase": random.random() * math.tau,
                "speed": random.uniform(.03, .08),
            })

    def _gen_stars(self):
        self.stars = []
        layers = [
            (46, 14, (1, 1.6), .35),
            (34, 30, (1.2, 2.2), .55),
            (22, 58, (1.6, 3.0), .9),
        ]
        for count, speed, size_range, alpha in layers:
            for _ in range(count):
                self.stars.append({
                    "x": random.uniform(0, max(1, self.width)),
                    "y": random.uniform(0, max(1, self.height)),
                    "speed": speed,
                    "size": random.uniform(*size_range),
                    "alpha": alpha,
                    "phase": random.random() * math.tau,
                })

    def trigger_shake(self, mag, duration):
        self.shake_mag = max(self.shake_mag, mag)
        self.shake_time = max(self.shake_time, duration)
        self.shake_total = max(self.shake_total, duration)

    def trigger_flash(self, color, duration=0.22):
        self.flash_color = color
        self.flash_time = duration
        self.flash_total = duration

    def spawn_text(self, x, y, text, color=(1, 1, 1), font_size=18, vy=62, life=0.85):
        self.damage_texts.append(DamageText(x, y, text, color, font_size, vy, life))

    def spawn_shockwave(self, x, y, color, max_radius=90, life=0.45, width=3.2):
        self.shockwaves.append(Shockwave(x, y, color, max_radius, life, width))

    def _glow(self, x, y, radius, color, layers=4, alpha=1.0):
        r, g, b = color[0], color[1], color[2]
        for i in range(layers, 0, -1):
            t = i / layers
            rad = radius * (1 + (layers - i) * .4)
            a = alpha * (0.14 * t)
            Color(r, g, b, a)
            Ellipse(pos=(x - rad, y - rad), size=(rad * 2, rad * 2))
        Color(r, g, b, min(1, alpha))
        Ellipse(pos=(x - radius * .55, y - radius * .55), size=(radius * 1.1, radius * 1.1))

    # ---------------------------------------------------------------

    def _resize(self, *_):
        if self.player_x == 0:
            self.player_x = self.width * .5
            self.player_y = self.height * .18
        else:
            self.player_x = clamp(self.player_x, 35, max(35, self.width - 35))
            self.player_y = clamp(self.player_y, 35, max(35, self.height - 35))
        self._gen_stars()
        self.redraw()

    def start(self):
        self.score = 0
        self.stage = 1
        self.wave = 0
        self.player_x = self.width * .5
        self.player_y = self.height * .18
        self.player_hp = self.player_max_hp
        self.shield = self.max_shield
        self.combo = 0
        self.combo_timer = 0
        self.enemies.clear()
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.particles.clear()
        self.items.clear()
        self.damage_texts.clear()
        self.shockwaves.clear()
        self.boss = None
        self.game_over = False
        self.paused = False
        self.running = True
        self.spawn_timer = .2
        self.last_time = time.monotonic()
        self._update_hud()
        self.redraw()

    def set_paused(self, value):
        self.paused = value

    def fire(self):
        if not self.running or self.paused or self.game_over:
            return
        if self.fire_timer > 0:
            return

        lvl = self.weapon_levels[self.weapon]
        if self.weapon == 0:
            cooldown, damage, spread, count = .25, 18 + lvl * 5, 0, 1
        elif self.weapon == 1:
            cooldown, damage, spread, count = .62, 13 + lvl * 4, .22, 5
        else:
            cooldown, damage, spread, count = .075, 9 + lvl * 2, .055, 1

        self.fire_timer = cooldown
        wcolor = self.WEAPON_COLORS[self.weapon]
        base = math.pi / 2
        for i in range(count):
            a = base
            if count > 1:
                a += (i - (count - 1) / 2) * spread
            speed = 610
            self.bullets.append(
                Bullet(self.player_x, self.player_y + 25,
                       math.cos(a) * speed, math.sin(a) * speed,
                       damage, 5 if self.weapon != 1 else 6, color=wcolor)
            )
        for _ in range(4):
            self.particles.append(Particle(self.player_x, self.player_y + 20, wcolor, .35))
        self.muzzle_flash = 0.07
        self.trigger_shake(1.4, 0.06)

    def move_player(self, x, y):
        if not self.running or self.paused:
            return
        self.player_x = clamp(x, 30, max(30, self.width - 30))
        self.player_y = clamp(y, 30, max(30, self.height - 30))

    def spawn_enemy(self):
        margin = 45
        x = random.uniform(margin, max(margin, self.width - margin))
        y = self.height + 50
        r = random.random()
        if self.stage >= 5 and r < .12:
            kind = "elite"
        elif r < .24:
            kind = "tank"
        elif r < .48:
            kind = "shooter"
        else:
            kind = "scout"
        self.enemies.append(Enemy(kind, x, y, int(self.stage)))

    def spawn_item(self, x, y):
        if random.random() > .16:
            return
        kind = random.choice(["coin", "heal", "shield", "rapid"])
        self.items.append({"x": x, "y": y, "kind": kind, "life": 8,
                            "phase": random.random() * math.tau})

    def damage_player(self, damage):
        if self.invincible > 0:
            return
        if self.shield > 0:
            absorbed = min(self.shield, damage)
            self.shield -= absorbed
            damage -= absorbed
        if damage > 0:
            self.player_hp -= damage
            self.spawn_text(self.player_x, self.player_y + 30, f"-{int(damage)}",
                             color=(1, .3, .3), font_size=17, vy=50, life=.6)
        self.invincible = .45
        self.trigger_shake(7, .22)
        self.trigger_flash((1, .15, .15), .18)
        for _ in range(12):
            self.particles.append(Particle(self.player_x, self.player_y, (1, .2, .2), .7))
        if self.player_hp <= 0:
            self.end_game()

    def add_xp(self, amount):
        self.xp += amount
        need = 100 + (self.player_level - 1) * 55
        while self.xp >= need:
            self.xp -= need
            self.player_level += 1
            self.player_max_hp += 10
            self.max_shield += 5
            self.player_hp = self.player_max_hp
            self.shield = self.max_shield
            need = 100 + (self.player_level - 1) * 55
            self.trigger_flash((1, .85, .2), .35)
            self.trigger_shake(5, .3)
            self.spawn_text(self.player_x, self.player_y + 60, "LEVEL UP!",
                             color=(1, .9, .25), font_size=26, vy=45, life=1.2)
            self.spawn_shockwave(self.player_x, self.player_y, (1, .85, .3), 140, .6, 4)

    def kill_enemy(self, enemy):
        self.combo = min(20, self.combo + 1)
        self.combo_timer = 2.5
        mult = 1 + self.combo * .05
        reward = int(enemy.reward * mult)
        self.coins += reward
        self.score += reward * 10
        self.add_xp(enemy.xp)
        self.spawn_item(enemy.x, enemy.y)
        self.spawn_shockwave(enemy.x, enemy.y, enemy.glow, enemy.size * 2.6, .35, 2.6)
        self.spawn_text(enemy.x, enemy.y, f"+{reward}", color=(1, .85, .3), font_size=15, life=.6)
        if self.combo >= 3 and self.combo % 3 == 0:
            self.spawn_text(enemy.x, enemy.y + 26, f"COMBO x{self.combo}!",
                             color=(1, .5, .95), font_size=17, life=.7)
        self.trigger_shake(1.6, .08)
        for _ in range(20):
            self.particles.append(Particle(enemy.x, enemy.y, (1, .35, .1), 1.0))

    def kill_boss(self):
        reward = 250 + int(self.stage) * 60
        self.coins += reward
        self.score += reward * 10
        self.add_xp(100 + int(self.stage) * 10)
        self.spawn_shockwave(self.boss.x, self.boss.y, (1, .3, .5), 260, .8, 5)
        self.spawn_shockwave(self.boss.x, self.boss.y, (1, .85, .2), 340, 1.0, 3)
        self.spawn_text(self.boss.x, self.boss.y, "BOSS DESTROYED", color=(1, .3, .4),
                         font_size=24, vy=30, life=1.3)
        self.trigger_flash((1, .8, .3), .45)
        self.trigger_shake(14, .5)
        for _ in range(70):
            self.particles.append(Particle(self.boss.x, self.boss.y, (1, .75, .1), 1.7))
        self.boss = None
        self.stage += 1
        self.wave = 0
        self.wave_target = 8 + int(self.stage) * 2
        self.spawn_timer = 1.0

    def next_wave(self):
        self.wave += 1
        if self.wave > self.wave_target:
            if self.boss is None:
                self.boss = Boss(int(self.stage), self.width * .5, self.height * .82)
                self.spawn_text(self.boss.x, self.boss.y + 90, "WARNING: BOSS",
                                 color=(1, .25, .3), font_size=22, vy=10, life=1.4)
                self.trigger_shake(8, .4)
            return
        self.spawn_enemy()

    def end_game(self):
        self.running = False
        self.game_over = True
        self.high_score = max(self.high_score, int(self.score))
        self.save.update({
            "coins": int(self.coins),
            "high_score": int(self.high_score),
            "weapon_levels": self.weapon_levels,
            "player_level": int(self.player_level),
            "xp": int(self.xp),
            "best_stage": max(int(self.save.get("best_stage", 1)), int(self.stage)),
        })
        save_game(self.save)
        self._update_hud()

    def buy_upgrade(self, weapon_index):
        lvl = self.weapon_levels[weapon_index]
        price = 100 * lvl
        if self.coins >= price:
            self.coins -= price
            self.weapon_levels[weapon_index] += 1
            self.save["weapon_levels"] = self.weapon_levels
            self.save["coins"] = self.coins
            save_game(self.save)
            return True
        return False

    def tick(self, _dt):
        now = time.monotonic()
        dt = min(.035, now - self.last_time)
        self.last_time = now
        self.time += dt

        # FX timers keep decaying even while paused/menu so effects settle.
        self.shake_time = max(0, self.shake_time - dt)
        self.flash_time = max(0, self.flash_time - dt)
        self.muzzle_flash = max(0, self.muzzle_flash - dt)
        for star in self.stars:
            star["y"] -= star["speed"] * dt * 6
            if star["y"] < -6:
                star["y"] = self.height + 6
                star["x"] = random.uniform(0, max(1, self.width))
        for dtext in list(self.damage_texts):
            if not dtext.update(dt):
                self.damage_texts.remove(dtext)
        for sw in list(self.shockwaves):
            if not sw.update(dt):
                self.shockwaves.remove(sw)

        if not self.running or self.paused:
            self.redraw()
            return

        self.fire_timer = max(0, self.fire_timer - dt)
        self.invincible = max(0, self.invincible - dt)
        self.combo_timer -= dt
        if self.combo_timer <= 0:
            self.combo = 0

        # Mild passive shield recharge.
        self.shield = min(self.max_shield, self.shield + dt * 1.7)

        # Faint engine trail while flying.
        if random.random() < 0.55:
            self.particles.append(
                Particle(self.player_x + random.uniform(-8, 8), self.player_y - 22,
                         (.25, .55, 1), power=.28, size_mult=1.1)
            )

        self.spawn_timer -= dt
        if self.spawn_timer <= 0 and self.boss is None:
            self.spawn_timer = max(.25, .9 - self.stage * .025)
            self.next_wave()

        for e in list(self.enemies):
            e.update(dt, self)
            if e.y < -70 or e.x < -100 or e.x > self.width + 100:
                self.enemies.remove(e)
                continue
            if math.hypot(e.x - self.player_x, e.y - self.player_y) < e.size + 23:
                self.damage_player(15 + int(self.stage))
                if e in self.enemies:
                    self.enemies.remove(e)

        if self.boss:
            self.boss.update(dt, self)
            if math.hypot(self.boss.x - self.player_x, self.boss.y - self.player_y) < self.boss.size + 25:
                self.damage_player(25 + int(self.stage) * 2)

        for b in list(self.bullets):
            if not b.update(dt):
                self.bullets.remove(b)
                continue
            hit = False
            for e in list(self.enemies):
                if math.hypot(b.x - e.x, b.y - e.y) < b.radius + e.size:
                    e.hp -= b.damage
                    e.flash = .08
                    hit = True
                    for _ in range(5):
                        self.particles.append(Particle(b.x, b.y, (1, .8, .2), .3))
                    if e.hp <= 0:
                        self.kill_enemy(e)
                        if e in self.enemies:
                            self.enemies.remove(e)
                    break
            if not hit and self.boss:
                if math.hypot(b.x - self.boss.x, b.y - self.boss.y) < b.radius + self.boss.size:
                    self.boss.hp -= b.damage
                    self.boss.flash = .08
                    hit = True
                    for _ in range(5):
                        self.particles.append(Particle(b.x, b.y, (1, .4, .1), .3))
                    if self.boss.hp <= 0:
                        self.kill_boss()
            if hit and b in self.bullets:
                self.bullets.remove(b)

        for b in list(self.enemy_bullets):
            if not b.update(dt):
                self.enemy_bullets.remove(b)
                continue
            if math.hypot(b.x - self.player_x, b.y - self.player_y) < b.radius + 21:
                self.damage_player(b.damage)
                if b in self.enemy_bullets:
                    self.enemy_bullets.remove(b)

        for item in list(self.items):
            item["y"] -= 45 * dt
            item["life"] -= dt
            if math.hypot(item["x"] - self.player_x, item["y"] - self.player_y) < 30:
                k = item["kind"]
                if k == "coin":
                    self.coins += 25
                    self.spawn_text(item["x"], item["y"], "+25", color=(1, .85, .3), font_size=14, life=.5)
                elif k == "heal":
                    self.player_hp = min(self.player_max_hp, self.player_hp + 30)
                    self.spawn_text(item["x"], item["y"], "+HP", color=(.3, 1, .4), font_size=14, life=.5)
                elif k == "shield":
                    self.shield = min(self.max_shield, self.shield + 40)
                    self.spawn_text(item["x"], item["y"], "+SHIELD", color=(.3, .7, 1), font_size=14, life=.5)
                elif k == "rapid":
                    self.fire_timer = 0
                    self.spawn_text(item["x"], item["y"], "RAPID FIRE!", color=(1, .3, 1), font_size=14, life=.5)
                    # A burst of immediate shots.
                    for _ in range(6):
                        self.bullets.append(Bullet(self.player_x, self.player_y + 20,
                                                   0, 680, 22, 5, color=self.WEAPON_COLORS[self.weapon]))
                self.items.remove(item)
            elif item["life"] <= 0:
                self.items.remove(item)

        for p in list(self.particles):
            if not p.update(dt):
                self.particles.remove(p)

        self.score += dt * (2 + self.stage)
        self._update_hud()
        self.redraw()

    def _update_hud(self):
        app = App.get_running_app()
        if app and hasattr(app, "hud"):
            hp = max(0, int(self.player_hp))
            sh = max(0, int(self.shield))
            boss = ""
            if self.boss:
                boss = f"   BOSS {int(self.boss.hp)}/{int(self.boss.max_hp)}"
            combo = f"   COMBO x{self.combo}" if self.combo > 1 else ""
            app.hud.text = (
                f"[b]❤️ {hp}/{int(self.player_max_hp)}   🛡 {sh}/{int(self.max_shield)}   "
                f"🪙 {int(self.coins)}   ⭐ {int(self.score)}   "
                f"Lv {int(self.player_level)}   W{self.weapon+1}{boss}{combo}[/b]"
            )

    # ---------------------------------------------------------------
    # RENDER
    # ---------------------------------------------------------------
    def redraw(self):
        self.canvas.clear()
        with self.canvas:
            # ---- deep space background ----
            Color(.02, .025, .06, 1)
            Rectangle(pos=self.pos, size=self.size)

            # ---- drifting nebula glow blobs (behind everything) ----
            for n in self.nebula:
                cx = n["rx"] * self.width + math.sin(self.time * n["speed"] + n["phase"]) * 40
                cy = n["ry"] * self.height + math.cos(self.time * n["speed"] * .8 + n["phase"]) * 30
                r, g, b = n["color"]
                for i, (mult, a) in enumerate(((1.0, .05), (.65, .07), (.35, .09))):
                    rad = n["r"] * mult
                    Color(r, g, b, a)
                    Ellipse(pos=(cx - rad, cy - rad), size=(rad * 2, rad * 2))

            # ---- parallax twinkling starfield ----
            for star in self.stars:
                twinkle = 0.65 + 0.35 * math.sin(self.time * 2.2 + star["phase"])
                Color(.75, .85, 1, star["alpha"] * twinkle)
                s = star["size"]
                Ellipse(pos=(star["x"], star["y"]), size=(s, s))

            # ---- screen shake applies to gameplay layer only ----
            PushMatrix()
            shake_x = shake_y = 0
            if self.shake_time > 0:
                ratio = self.shake_time / self.shake_total
                mag = self.shake_mag * ratio
                shake_x = random.uniform(-mag, mag)
                shake_y = random.uniform(-mag, mag)
            Translate(shake_x, shake_y)

            # Arena edge glow
            Color(.2, .35, .55, .35)
            Line(rectangle=(8, 8, max(0, self.width - 16), max(0, self.height - 16)), width=1.2)

            # ---- shockwave rings ----
            for sw in self.shockwaves:
                alpha = max(0, sw.life / sw.max_life)
                Color(sw.color[0], sw.color[1], sw.color[2], alpha * .8)
                Line(circle=(sw.x, sw.y, sw.radius), width=sw.width * alpha + .5)

            # ---- items (glowing, pulsing, with icon shapes) ----
            for item in self.items:
                x, y = item["x"], item["y"]
                pulse = 1 + 0.18 * math.sin(self.time * 6 + item["phase"])
                if item["kind"] == "coin":
                    c = (1, .8, .15)
                elif item["kind"] == "heal":
                    c = (.25, 1, .35)
                elif item["kind"] == "shield":
                    c = (.25, .65, 1)
                else:
                    c = (1, .25, 1)
                self._glow(x, y, 13 * pulse, c, layers=3)
                Color(1, 1, 1, .85)
                if item["kind"] == "coin":
                    Line(circle=(x, y, 7 * pulse), width=1.4)
                elif item["kind"] == "heal":
                    Line(points=[x - 6, y, x + 6, y], width=2.2)
                    Line(points=[x, y - 6, x, y + 6], width=2.2)
                elif item["kind"] == "shield":
                    Line(points=poly_points(x, y, 8 * pulse, 6, self.time), width=1.6, close=True)
                else:
                    Line(points=[x - 4, y + 7, x + 2, y + 1, x - 2, y - 1, x + 4, y - 7],
                         width=1.8)

            # ---- player bullets (glow + streak trail) ----
            for b in self.bullets:
                Color(*b.color, .35)
                Line(points=[b.x, b.y, b.x - b.vx * .018, b.y - b.vy * .018],
                     width=b.radius * .9)
                self._glow(b.x, b.y, b.radius * 1.7, b.color, layers=3)

            # ---- enemy bullets ----
            for b in self.enemy_bullets:
                Color(*b.color, .35)
                Line(points=[b.x, b.y, b.x - b.vx * .018, b.y - b.vy * .018],
                     width=b.radius * .9)
                self._glow(b.x, b.y, b.radius * 1.6, b.color, layers=3)

            # ---- enemies: rotating glowing polygons ----
            for e in self.enemies:
                glow_c = (1, 1, 1) if e.flash > 0 else e.glow
                self._glow(e.x, e.y, e.size * 1.15, glow_c, layers=3, alpha=.9)
                body_c = (1, 1, 1) if e.flash > 0 else e.color
                Color(*body_c, 1)
                if e.kind == "elite":
                    pts = star_points(e.x, e.y, e.size, e.size * .5, 5, e.rot)
                else:
                    pts = poly_points(e.x, e.y, e.size, e.sides, e.rot)
                Line(points=pts, width=2.4, close=True)
                Color(*body_c, .35)
                Ellipse(pos=(e.x - e.size * .5, e.y - e.size * .5), size=(e.size, e.size))
                # HP bar with glow backing
                Color(0, 0, 0, .55)
                RoundedRectangle(pos=(e.x - e.size, e.y + e.size + 5), size=(e.size * 2, 5), radius=[2])
                hp_ratio = max(0, e.hp / e.max_hp)
                hp_color = (.25, 1, .3) if hp_ratio > .4 else (1, .65, .15) if hp_ratio > .18 else (1, .2, .2)
                Color(*hp_color, 1)
                RoundedRectangle(pos=(e.x - e.size, e.y + e.size + 5),
                                 size=(e.size * 2 * hp_ratio, 5), radius=[2])

            # ---- boss: big pulsating aura + spinning spike ring ----
            if self.boss:
                b = self.boss
                pulse = 1 + .06 * math.sin(self.time * 4)
                boss_c = (1, 1, 1) if b.flash > 0 else (1, .12, .4)
                self._glow(b.x, b.y, b.size * 1.3 * pulse, (1, .1, .4), layers=5, alpha=1)
                Color(1, .5, .7, .6)
                Line(points=star_points(b.x, b.y, b.size * 1.25, b.size * .95, 10, b.rot),
                     width=2, close=True)
                Color(*boss_c, 1)
                Ellipse(pos=(b.x - b.size, b.y - b.size), size=(b.size * 2, b.size * 2))
                Color(1, 1, 1, .25)
                Ellipse(pos=(b.x - b.size * .4, b.y - b.size * .4), size=(b.size * .8, b.size * .8))
                # HP bar
                Color(0, 0, 0, .6)
                RoundedRectangle(pos=(b.x - 102, b.y + b.size + 12), size=(204, 12), radius=[4])
                Color(1, .12, .3, 1)
                RoundedRectangle(pos=(b.x - 100, b.y + b.size + 14),
                                 size=(200 * max(0, b.hp / b.max_hp), 8), radius=[3])

            # ---- player ship: engine flame + glow hull ----
            if self.invincible <= 0 or int(self.invincible * 20) % 2 == 0:
                flicker = 0.6 + 0.4 * math.sin(self.time * 25)
                flame_len = 14 + 8 * flicker
                Color(.3, .6, 1, .55 * flicker)
                Line(points=[
                    self.player_x - 9, self.player_y - 14,
                    self.player_x, self.player_y - 14 - flame_len,
                    self.player_x + 9, self.player_y - 14,
                ], width=2, close=True)

                hull_c = self.WEAPON_COLORS[self.weapon]
                self._glow(self.player_x, self.player_y + 5, 22, hull_c, layers=3, alpha=.7)
                Color(.85, .93, 1, 1)
                Line(points=[
                    self.player_x, self.player_y + 28,
                    self.player_x - 21, self.player_y - 22,
                    self.player_x, self.player_y - 12,
                    self.player_x + 21, self.player_y - 22,
                    self.player_x, self.player_y + 28
                ], close=True, width=2.4)
                Color(*hull_c, .9)
                Ellipse(pos=(self.player_x - 6, self.player_y - 5), size=(12, 12))

                if self.muzzle_flash > 0:
                    self._glow(self.player_x, self.player_y + 32, 14, hull_c, layers=3, alpha=1)

            # ---- ambient particles (glow for bigger ones) ----
            for p in self.particles:
                alpha = max(0, p.life / p.max_life)
                if p.size > 4:
                    self._glow(p.x, p.y, p.size, p.color, layers=2, alpha=alpha * .8)
                else:
                    Color(p.color[0], p.color[1], p.color[2], alpha)
                    Ellipse(pos=(p.x - p.size / 2, p.y - p.size / 2), size=(p.size, p.size))

            # ---- floating damage / combo / level-up text ----
            for dt_ in self.damage_texts:
                if dt_.texture is None:
                    continue
                alpha = max(0, dt_.life / dt_.max_life)
                Color(1, 1, 1, alpha)
                Rectangle(texture=dt_.texture,
                          pos=(dt_.x - dt_.size[0] / 2, dt_.y),
                          size=dt_.size)

            # ---- virtual joystick ----
            if self.joy_start:
                jx, jy = self.joy_start
                Color(.3, .6, 1, .18)
                Ellipse(pos=(jx-55, jy-55), size=(110, 110))
                if self.joy_pos:
                    Color(.4, .75, 1, .38)
                    Ellipse(pos=(self.joy_pos[0]-25, self.joy_pos[1]-25), size=(50, 50))

            PopMatrix()

            # ---- full-screen flash overlay (damage / level-up / boss kill) ----
            if self.flash_time > 0:
                ratio = self.flash_time / self.flash_total
                Color(self.flash_color[0], self.flash_color[1], self.flash_color[2], .32 * ratio)
                Rectangle(pos=self.pos, size=self.size)

    def on_touch_down(self, touch):
        if not self.running or self.paused:
            return super().on_touch_down(touch)

        # Right-side touch = fire. Left side = virtual joystick.
        if touch.x > self.width * .72:
            self.fire_touch = touch.uid
            self.fire()
            return True

        self.touch_id = touch.uid
        self.joy_start = (touch.x, touch.y)
        self.joy_pos = self.joy_start
        return True

    def on_touch_move(self, touch):
        if touch.uid == self.touch_id and self.joy_start:
            sx, sy = self.joy_start
            dx, dy = touch.x - sx, touch.y - sy
            d = max(1, math.hypot(dx, dy))
            maxd = 65
            k = min(1, maxd / d)
            self.joy_pos = (sx + dx*k, sy + dy*k)
            # Continuous movement
            self.move_player(
                self.player_x + dx * .055,
                self.player_y + dy * .055
            )
            return True
        if touch.uid == self.fire_touch:
            self.fire()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.uid == self.touch_id:
            self.touch_id = None
            self.joy_start = None
            self.joy_pos = None
            self.redraw()
            return True
        if touch.uid == self.fire_touch:
            self.fire_touch = None
            return True
        return super().on_touch_up(touch)


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = FloatLayout()
        self.game = GameWorld()
        root.add_widget(self.game)

        # HUD
        self.hud = Label(
            text="SPACE SHOOTER 2.0",
            size_hint=(1, None),
            height=dp(38),
            pos_hint={"top": 1},
            font_size="13sp",
            bold=True,
            markup=True,
        )
        root.add_widget(self.hud)

        # Buttons
        self.pause_btn = Button(
            text="Ⅱ",
            size_hint=(None, None),
            size=(dp(54), dp(48)),
            pos_hint={"right": 1, "top": 1},
            font_size="20sp",
        )
        self.pause_btn.bind(on_release=self.toggle_pause)
        root.add_widget(self.pause_btn)

        self.shop_btn = Button(
            text="SHOP",
            size_hint=(None, None),
            size=(dp(78), dp(42)),
            pos_hint={"right": .99, "y": .02},
            font_size="11sp",
        )
        self.shop_btn.bind(on_release=self.open_shop)
        root.add_widget(self.shop_btn)

        self.weapon_btn = Button(
            text="WEAPON",
            size_hint=(None, None),
            size=(dp(92), dp(42)),
            pos_hint={"x": .01, "y": .02},
            font_size="11sp",
        )
        self.weapon_btn.bind(on_release=self.next_weapon)
        root.add_widget(self.weapon_btn)

        self.fire_label = Label(
            text="FIRE",
            size_hint=(None, None),
            size=(dp(95), dp(65)),
            pos_hint={"right": .99, "y": .10},
            font_size="16sp",
            bold=True,
        )
        root.add_widget(self.fire_label)

        self.add_widget(root)

    def on_pre_enter(self):
        self.game.start()
        App.get_running_app().hud = self.hud

    def toggle_pause(self, *_):
        self.game.paused = not self.game.paused
        self.pause_btn.text = "▶" if self.game.paused else "Ⅱ"

    def next_weapon(self, *_):
        self.game.weapon = (self.game.weapon + 1) % 3
        self.game._update_hud()

    def open_shop(self, *_):
        self.manager.current = "shop"


class ShopScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = FloatLayout()
        self.title = Label(
            text="ARMORY",
            font_size="28sp",
            bold=True,
            size_hint=(1, None),
            height=dp(60),
            pos_hint={"top": .96},
        )
        self.info = Label(
            text="",
            font_size="15sp",
            size_hint=(1, None),
            height=dp(45),
            pos_hint={"top": .84},
        )
        self.layout.add_widget(self.title)
        self.layout.add_widget(self.info)

        self.buttons = []
        names = ["PISTOL", "SHOTGUN", "MACHINE GUN"]
        for i, name in enumerate(names):
            b = Button(
                text=name,
                size_hint=(.8, None),
                height=dp(65),
                pos_hint={"center_x": .5, "top": .70 - i*.18},
                font_size="16sp",
            )
            b.bind(on_release=lambda btn, idx=i: self.upgrade(idx))
            self.layout.add_widget(b)
            self.buttons.append(b)

        back = Button(
            text="BACK TO GAME",
            size_hint=(.65, None),
            height=dp(55),
            pos_hint={"center_x": .5, "y": .04},
        )
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "game"))
        self.layout.add_widget(back)
        self.add_widget(self.layout)

    def on_pre_enter(self):
        g = self.manager.get_screen("game").game
        self.info.text = f"Coins: {int(g.coins)}   |   Player Lv: {int(g.player_level)}"
        for i, b in enumerate(self.buttons):
            lvl = g.weapon_levels[i]
            price = 100 * lvl
            b.text = f"{['PISTOL','SHOTGUN','MACHINE GUN'][i]}  •  Lv {lvl}  •  Upgrade {price} 🪙"

    def upgrade(self, idx):
        g = self.manager.get_screen("game").game
        g.buy_upgrade(idx)
        self.on_pre_enter()


class MenuScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = FloatLayout()
        title = Label(
            text="SPACE SHOOTER\n2.0",
            font_size="38sp",
            bold=True,
            halign="center",
            size_hint=(1, None),
            height=dp(130),
            pos_hint={"center_x": .5, "top": .88},
        )
        layout.add_widget(title)

        subtitle = Label(
            text="MOBILE EDITION",
            font_size="14sp",
            size_hint=(1, None),
            height=dp(35),
            pos_hint={"center_x": .5, "top": .65},
        )
        layout.add_widget(subtitle)

        start = Button(
            text="START GAME",
            size_hint=(.72, None),
            height=dp(65),
            pos_hint={"center_x": .5, "center_y": .48},
            font_size="20sp",
        )
        start.bind(on_release=lambda *_: setattr(self.manager, "current", "game"))
        layout.add_widget(start)

        shop = Button(
            text="ARMORY",
            size_hint=(.72, None),
            height=dp(55),
            pos_hint={"center_x": .5, "center_y": .34},
        )
        shop.bind(on_release=lambda *_: setattr(self.manager, "current", "shop"))
        layout.add_widget(shop)

        info = Label(
            text="Touch left side to move • Hold right side to fire",
            font_size="12sp",
            size_hint=(1, None),
            height=dp(50),
            pos_hint={"center_x": .5, "y": .05},
        )
        layout.add_widget(info)
        self.add_widget(layout)


class GameApp(App):
    hud = None

    def build(self):
        Window.clearcolor = (.02, .025, .06, 1)
        sm = ScreenManager(transition=FadeTransition(duration=.18))
        sm.add_widget(MenuScreen(name="menu"))
        game_screen = MainScreen(name="game")
        sm.add_widget(game_screen)
        sm.add_widget(ShopScreen(name="shop"))
        self.game_screen = game_screen
        self.hud = game_screen.hud
        return sm


if __name__ == "__main__":
    GameApp().run()
