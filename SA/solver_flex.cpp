/**
 * solver_flex.cpp
 * Simulated Annealing solver for the Mecalux Warehouse Bay Placement challenge.
 * HackUPC 2026.
 *
 * Compile:
 *   g++ -O3 -std=c++17 -o solver_flex solver_flex.cpp
 *
 * Usage:
 *   ./solver_flex <warehouse.csv> <obstacles.csv> <ceiling.csv> <types_of_bays.csv> <output.csv>
 */

#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <random>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

// ---------------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------------
static auto g_start = std::chrono::steady_clock::now();
static inline double elapsed() {
    auto now = std::chrono::steady_clock::now();
    return std::chrono::duration<double>(now - g_start).count();
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
static constexpr double TIME_LIMIT = 28.0;
static constexpr double EPS        = 1e-6;

// ---------------------------------------------------------------------------
// Fast RNG: xoshiro256**
// ---------------------------------------------------------------------------
struct Rng {
    uint64_t s[4];

    explicit Rng(uint64_t seed = 12345678ULL) {
        // SplitMix64 seeding
        auto sm = [](uint64_t &x) -> uint64_t {
            x += 0x9e3779b97f4a7c15ULL;
            uint64_t z = x;
            z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
            z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
            return z ^ (z >> 31);
        };
        s[0] = sm(seed); s[1] = sm(seed); s[2] = sm(seed); s[3] = sm(seed);
    }

    uint64_t next() {
        const uint64_t r = ((s[1] * 5) << 7 | (s[1] * 5) >> 57) * 9;
        const uint64_t t = s[1] << 17;
        s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3];
        s[2] ^= t;
        s[3] = (s[3] << 45) | (s[3] >> 19);
        return r;
    }

    // [0, 1)
    double rand01() { return (next() >> 11) * (1.0 / (1ULL << 53)); }

    // [0, n)
    int randi(int n) { return (int)(rand01() * n); }
};

static Rng rng(std::chrono::steady_clock::now().time_since_epoch().count());

// ---------------------------------------------------------------------------
// 2D point / geometry
// ---------------------------------------------------------------------------
using Point = std::array<double, 2>;
using Quad  = std::array<Point, 4>;

static inline double cross2(const Point &o, const Point &a, const Point &b) {
    return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0]);
}

static Quad obb_corners(double x, double y, double w, double d, double angle_deg) {
    double rad   = angle_deg * (M_PI / 180.0);
    double cos_a = std::cos(rad);
    double sin_a = std::sin(rad);
    return {{
        {x,                             y                            },
        {x + w*cos_a,                   y + w*sin_a                  },
        {x + w*cos_a - d*sin_a,         y + w*sin_a + d*cos_a        },
        {x - d*sin_a,                   y + d*cos_a                  }
    }};
}

static void aabb_from_quad(const Quad &q,
                           double &x1, double &y1, double &x2, double &y2) {
    x1 = x2 = q[0][0]; y1 = y2 = q[0][1];
    for (int i = 1; i < 4; ++i) {
        if (q[i][0] < x1) x1 = q[i][0];
        if (q[i][0] > x2) x2 = q[i][0];
        if (q[i][1] < y1) y1 = q[i][1];
        if (q[i][1] > y2) y2 = q[i][1];
    }
}

// SAT overlap between two quads
static bool sat_overlap(const Quad &a, const Quad &b) {
    const Quad *polys[2] = {&a, &b};
    for (int pi = 0; pi < 2; ++pi) {
        const Quad &poly = *polys[pi];
        for (int i = 0; i < 4; ++i) {
            int j = (i + 1) & 3;
            double nx = poly[j][1] - poly[i][1];
            double ny = poly[i][0] - poly[j][0];
            double a_min = std::numeric_limits<double>::infinity();
            double a_max = -std::numeric_limits<double>::infinity();
            double b_min = std::numeric_limits<double>::infinity();
            double b_max = -std::numeric_limits<double>::infinity();
            for (const auto &p : a) {
                double v = p[0]*nx + p[1]*ny;
                if (v < a_min) a_min = v;
                if (v > a_max) a_max = v;
            }
            for (const auto &p : b) {
                double v = p[0]*nx + p[1]*ny;
                if (v < b_min) b_min = v;
                if (v > b_max) b_max = v;
            }
            if (a_max <= b_min + EPS || b_max <= a_min + EPS) return false;
        }
    }
    return true;
}

static bool segments_intersect(const Point &p1, const Point &p2,
                                const Point &p3, const Point &p4) {
    auto ccw = [](const Point &A, const Point &B, const Point &C) {
        return (C[1]-A[1])*(B[0]-A[0]) > (B[1]-A[1])*(C[0]-A[0]);
    };
    return (ccw(p1,p3,p4) != ccw(p2,p3,p4)) &&
           (ccw(p1,p2,p3) != ccw(p1,p2,p4));
}

// ---------------------------------------------------------------------------
// CSV parsing helpers
// ---------------------------------------------------------------------------
static std::vector<std::vector<double>> parse_csv(const std::string &path, int min_cols) {
    std::vector<std::vector<double>> rows;
    std::ifstream f(path);
    if (!f) { std::cerr << "Cannot open: " << path << "\n"; return rows; }
    std::string line;
    while (std::getline(f, line)) {
        // strip \r
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        std::vector<double> row;
        std::stringstream ss(line);
        std::string tok;
        while (std::getline(ss, tok, ',')) {
            // trim spaces
            size_t s = tok.find_first_not_of(" \t");
            if (s == std::string::npos) { row.push_back(0); continue; }
            tok = tok.substr(s);
            try { row.push_back(std::stod(tok)); }
            catch (...) { goto next_line; }
        }
        if ((int)row.size() >= min_cols) rows.push_back(row);
        next_line:;
    }
    return rows;
}

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------
struct BayType {
    int    id;
    double width, depth, height, gap;
    int    nLoads;
    double price;
    double threshold;   // = height
    double efficiency;  // = price / nLoads
};

struct PlacedBay {
    int    type_id;
    double x, y, rot;
    double x1, y1, x2, y2;  // AABB
    Quad   corners;
    Quad   bay_corners;
};

// ---------------------------------------------------------------------------
// Warehouse
// ---------------------------------------------------------------------------
class Warehouse {
public:
    std::vector<Point> verts;
    double area;
    double min_x, min_y, max_x, max_y;
    std::vector<double> wall_angles;

    void build(const std::vector<std::vector<double>> &raw) {
        for (auto &r : raw) verts.push_back({r[0], r[1]});
        // Shoelace
        area = 0;
        int n = (int)verts.size();
        for (int i = 0; i < n; ++i) {
            int j = (i+1) % n;
            area += verts[i][0]*verts[j][1] - verts[j][0]*verts[i][1];
        }
        area = std::abs(area) * 0.5;

        min_x = max_x = verts[0][0];
        min_y = max_y = verts[0][1];
        for (auto &v : verts) {
            min_x = std::min(min_x, v[0]); max_x = std::max(max_x, v[0]);
            min_y = std::min(min_y, v[1]); max_y = std::max(max_y, v[1]);
        }

        // Wall angles
        std::unordered_set<double> angle_set;
        for (int i = 0; i < n; ++i) {
            int j = (i+1) % n;
            double dx = verts[j][0] - verts[i][0];
            double dy = verts[j][1] - verts[i][1];
            double ang = std::fmod(std::atan2(dy, dx) * (180.0/M_PI) + 360.0, 360.0);
            for (int k = 0; k < 4; ++k)
                angle_set.insert(std::fmod(ang + 90.0*k, 360.0));
        }
        wall_angles.assign(angle_set.begin(), angle_set.end());
        if ((int)wall_angles.size() > 12) wall_angles.resize(12);
    }

    bool point_inside(double px, double py) const {
        int n = (int)verts.size();
        bool inside = false;
        int j = n - 1;
        for (int i = 0; i < n; j = i++) {
            double xi = verts[i][0], yi = verts[i][1];
            double xj = verts[j][0], yj = verts[j][1];
            if (((yi > py) != (yj > py))) {
                double x_int = (yj != yi) ? (xi + (py-yi)/(yj-yi)*(xj-xi)) : xi;
                if (px < x_int + EPS) inside = !inside;
            }
        }
        return inside;
    }

    bool obb_inside(const Quad &corners) const {
        double qx1, qy1, qx2, qy2;
        aabb_from_quad(corners, qx1, qy1, qx2, qy2);
        if (qx1 < min_x - EPS || qx2 > max_x + EPS) return false;
        if (qy1 < min_y - EPS || qy2 > max_y + EPS) return false;
        for (auto &c : corners)
            if (!point_inside(c[0], c[1])) return false;
        // Edge-wall intersection
        int n = (int)verts.size();
        for (int i = 0; i < 4; ++i) {
            const Point &p1 = corners[i];
            const Point &p2 = corners[(i+1)&3];
            for (int j = 0; j < n; ++j) {
                const Point &w1 = verts[j];
                const Point &w2 = verts[(j+1)%n];
                if (segments_intersect(p1, p2, w1, w2)) return false;
            }
        }
        return true;
    }
};

// ---------------------------------------------------------------------------
// Ceiling (step function)
// ---------------------------------------------------------------------------
class Ceiling {
public:
    std::vector<double> xs, hs;

    void build(const std::vector<std::vector<double>> &raw) {
        std::vector<std::pair<double,double>> pts;
        for (auto &r : raw) pts.push_back({r[0], r[1]});
        std::sort(pts.begin(), pts.end());
        for (auto &p : pts) { xs.push_back(p.first); hs.push_back(p.second); }
    }

    double height_at(double x) const {
        if (xs.empty()) return 1e18;
        if (x < xs[0]) return hs[0];
        // Binary search for rightmost xs[i] <= x
        int lo = 0, hi = (int)xs.size() - 1;
        while (lo < hi) {
            int mid = (lo + hi + 1) / 2;
            if (xs[mid] <= x) lo = mid; else hi = mid - 1;
        }
        return hs[lo];
    }

    double min_height(double x1, double x2) const {
        double h = height_at(x1);
        for (int i = 0; i < (int)xs.size(); ++i) {
            if (xs[i] > x2) break;
            if (xs[i] > x1 && hs[i] < h) h = hs[i];
        }
        return h;
    }
};

// ---------------------------------------------------------------------------
// Spatial Grid
// ---------------------------------------------------------------------------
class Grid {
public:
    double ox, oy, cs;
    int cols, rows;
    std::unordered_map<int, std::unordered_set<int>> cells;

    void build(double min_x, double min_y, double max_x, double max_y, double cell_size) {
        ox = min_x; oy = min_y; cs = cell_size;
        cols = std::max(1, (int)std::ceil((max_x - min_x) / cell_size));
        rows = std::max(1, (int)std::ceil((max_y - min_y) / cell_size));
    }

    void _range(double x1, double y1, double x2, double y2,
                int &c1, int &r1, int &c2, int &r2) const {
        c1 = std::max(0, (int)((x1-ox)/cs));
        c2 = std::min(cols-1, (int)((x2-ox)/cs));
        r1 = std::max(0, (int)((y1-oy)/cs));
        r2 = std::min(rows-1, (int)((y2-oy)/cs));
    }

    void insert(int idx, double x1, double y1, double x2, double y2) {
        int c1,r1,c2,r2; _range(x1,y1,x2,y2,c1,r1,c2,r2);
        for (int r = r1; r <= r2; ++r)
            for (int c = c1; c <= c2; ++c)
                cells[r*cols+c].insert(idx);
    }

    void remove(int idx, double x1, double y1, double x2, double y2) {
        int c1,r1,c2,r2; _range(x1,y1,x2,y2,c1,r1,c2,r2);
        for (int r = r1; r <= r2; ++r)
            for (int c = c1; c <= c2; ++c) {
                auto it = cells.find(r*cols+c);
                if (it != cells.end()) it->second.erase(idx);
            }
    }

    std::unordered_set<int> query(double x1, double y1, double x2, double y2) const {
        int c1,r1,c2,r2; _range(x1,y1,x2,y2,c1,r1,c2,r2);
        std::unordered_set<int> result;
        for (int r = r1; r <= r2; ++r)
            for (int c = c1; c <= c2; ++c) {
                auto it = cells.find(r*cols+c);
                if (it != cells.end())
                    result.insert(it->second.begin(), it->second.end());
            }
        return result;
    }
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
struct Snap { int type_id; double x, y, rot; };

class State {
public:
    const std::vector<BayType> &bay_types;
    const Warehouse             &wh;
    const Ceiling               &ceil;
    std::vector<std::array<double,4>> obs_rects; // x1,y1,x2,y2

    Grid grid;
    std::unordered_map<int, PlacedBay> bays;
    std::unordered_set<int> active;
    double sum_eff  = 0.0;
    double sum_area = 0.0;
    double wh_area;
    int    next_idx = 0;

    // Candidate corners for SA add moves
    std::vector<Point> candidate_corners;
    std::vector<double> base_xs, base_ys;

    // Feasibility cache: key = (type_id, rx*10, ry*10, rrot*10, excl)
    struct FKey {
        int tid; int rx, ry, rrot, excl;
        bool operator==(const FKey &o) const {
            return tid==o.tid && rx==o.rx && ry==o.ry && rrot==o.rrot && excl==o.excl;
        }
    };
    struct FKeyHash {
        size_t operator()(const FKey &k) const {
            size_t h = (size_t)k.tid * 2654435761ULL;
            h ^= (size_t)(k.rx + 1000000) * 805459861ULL;
            h ^= (size_t)(k.ry + 1000000) * 1597334677ULL;
            h ^= (size_t)(k.rrot + 3600)  * 2246822519ULL;
            h ^= (size_t)(k.excl + 2)     * 3266489917ULL;
            return h;
        }
    };
    std::unordered_map<FKey, bool, FKeyHash> fcache;

    State(const std::vector<BayType> &bt, const Warehouse &w,
          const std::vector<std::array<double,4>> &obs, const Ceiling &c)
        : bay_types(bt), wh(w), ceil(c), obs_rects(obs), wh_area(w.area)
    {
        double span = std::max(w.max_x - w.min_x, w.max_y - w.min_y);
        double cs   = std::max(50.0, span / 80.0);
        grid.build(w.min_x, w.min_y, w.max_x, w.max_y, cs);

        // Insert obstacles with negative indices
        for (int i = 0; i < (int)obs_rects.size(); ++i) {
            auto &o = obs_rects[i];
            grid.insert(-(i+2), o[0], o[1], o[2], o[3]);
        }

        // Base coords
        std::unordered_set<double> xs_set, ys_set;
        for (auto &v : wh.verts) { xs_set.insert(v[0]); ys_set.insert(v[1]); }
        for (auto &o : obs_rects) {
            xs_set.insert(o[0]); xs_set.insert(o[2]);
            ys_set.insert(o[1]); ys_set.insert(o[3]);
        }
        base_xs.assign(xs_set.begin(), xs_set.end());
        base_ys.assign(ys_set.begin(), ys_set.end());
        std::sort(base_xs.begin(), base_xs.end());
        std::sort(base_ys.begin(), base_ys.end());

        update_candidates();
    }

    void update_candidates() {
        std::unordered_set<long long> seen;
        auto add_pt = [&](double x, double y) {
            long long key = (long long)(std::round(x)) * 1000007LL +
                            (long long)(std::round(y));
            if (seen.insert(key).second) candidate_corners.push_back({x, y});
        };
        candidate_corners.clear();
        for (auto &v : wh.verts) add_pt(v[0], v[1]);
        for (auto &o : obs_rects) {
            add_pt(o[0], o[1]); add_pt(o[2], o[1]);
            add_pt(o[0], o[3]); add_pt(o[2], o[3]);
        }
        for (int idx : active) {
            auto &b = bays[idx];
            add_pt(b.x1, b.y1); add_pt(b.x2, b.y1);
            add_pt(b.x1, b.y2); add_pt(b.x2, b.y2);
        }
    }

    double quality() const {
        if (active.empty()) return 1e18;
        double exp = 2.0 - (sum_area / wh_area);
        return std::pow(sum_eff, exp);
    }

    bool feasible(const BayType &bt, double x, double y, double rot, int excl = -1) {
        // Cache lookup
        FKey key{ bt.id,
                  (int)std::round(x * 10),
                  (int)std::round(y * 10),
                  (int)std::round(rot * 10),
                  excl };
        auto it = fcache.find(key);
        if (it != fcache.end()) return it->second;

        double w = bt.width;
        double d_full = bt.depth + bt.gap;
        double d_bay = bt.depth;
        Quad corners_f = obb_corners(x, y, w, d_full, rot);
        Quad corners_b = obb_corners(x, y, w, d_bay, rot);
        double qx1, qy1, qx2, qy2;
        aabb_from_quad(corners_f, qx1, qy1, qx2, qy2);

        // Warehouse containment
        if (!wh.obb_inside(corners_f)) { fcache[key] = false; return false; }

        // Ceiling
        if (ceil.min_height(qx1, qx2) < bt.threshold - EPS) {
            fcache[key] = false; return false;
        }

        // Collision
        auto cands = grid.query(qx1, qy1, qx2, qy2);
        for (int idx : cands) {
            if (idx == excl) continue;
            if (idx < 0) {
                // Obstacle
                auto &o = obs_rects[-(idx+2)];
                Quad oc = {{
                    {o[0],o[1]}, {o[2],o[1]}, {o[2],o[3]}, {o[0],o[3]}
                }};
                if (sat_overlap(corners_f, oc)) { fcache[key] = false; return false; }
            } else if (active.count(idx)) {
                const auto &b = bays.at(idx);
                if (sat_overlap(corners_b, b.corners) || sat_overlap(b.bay_corners, corners_f)) {
                    fcache[key] = false; return false;
                }
            }
        }
        fcache[key] = true;
        return true;
    }

    int add(const BayType &bt, double x, double y, double rot) {
        fcache.clear();
        double w = bt.width;
        double d_full = bt.depth + bt.gap;
        double d_bay = bt.depth;
        Quad   corners_f = obb_corners(x, y, w, d_full, rot);
        Quad   corners_b = obb_corners(x, y, w, d_bay, rot);
        double qx1, qy1, qx2, qy2;
        aabb_from_quad(corners_f, qx1, qy1, qx2, qy2);

        PlacedBay pb;
        pb.type_id = bt.id;
        pb.x = x; pb.y = y; pb.rot = rot;
        pb.x1 = qx1; pb.y1 = qy1; pb.x2 = qx2; pb.y2 = qy2;
        pb.corners = corners_f;
        pb.bay_corners = corners_b;

        int idx = next_idx++;
        bays[idx] = pb;
        active.insert(idx);
        grid.insert(idx, qx1, qy1, qx2, qy2);
        sum_eff  += bt.efficiency;
        sum_area += bt.width * bt.depth;  // no gap
        return idx;
    }

    PlacedBay remove(int idx) {
        fcache.clear();
        PlacedBay pb = bays[idx];
        const BayType &bt = bay_types[pb.type_id];
        grid.remove(idx, pb.x1, pb.y1, pb.x2, pb.y2);
        active.erase(idx);
        sum_eff  -= bt.efficiency;
        sum_area -= bt.width * bt.depth;  // no gap
        return pb;
    }

    std::vector<Snap> snapshot() const {
        std::vector<Snap> s;
        s.reserve(active.size());
        for (int idx : active) {
            auto &b = bays.at(idx);
            s.push_back({b.type_id, b.x, b.y, b.rot});
        }
        return s;
    }

    void restore(const std::vector<Snap> &snap) {
        for (int idx : std::vector<int>(active.begin(), active.end()))
            remove(idx);
        bays.clear();
        active.clear();
        next_idx = 0;
        for (auto &s : snap)
            add(bay_types[s.type_id], s.x, s.y, s.rot);
    }

    // Raw re-insert for undo (bypasses cache clear, does NOT call add())
    void raw_reinsert(int idx, const PlacedBay &pb) {
        bays[idx] = pb;
        active.insert(idx);
        grid.insert(idx, pb.x1, pb.y1, pb.x2, pb.y2);
        const BayType &bt = bay_types[pb.type_id];
        sum_eff  += bt.efficiency;
        sum_area += bt.width * bt.depth;  // IMPORTANT: no gap, not AABB
    }
};

// ---------------------------------------------------------------------------
// Greedy
// ---------------------------------------------------------------------------
static void greedy(State &state, double time_limit) {
    double t0 = elapsed();

    std::vector<int> sorted_idx;
    for (int i = 0; i < (int)state.bay_types.size(); ++i)
        sorted_idx.push_back(i);
    std::sort(sorted_idx.begin(), sorted_idx.end(), [&](int a, int b) {
        return state.bay_types[a].efficiency < state.bay_types[b].efficiency;
    });

    // Build test angles
    std::vector<double> test_angles = state.wh.wall_angles;
    for (double a : {0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0})
        test_angles.push_back(a);
    // Deduplicate
    std::sort(test_angles.begin(), test_angles.end());
    test_angles.erase(std::unique(test_angles.begin(), test_angles.end()), test_angles.end());
    if ((int)test_angles.size() > 12) test_angles.resize(12);

    double half = time_limit * 0.5;
    int total = 0;

    // Pass 1: strip packing
    for (int ti : sorted_idx) {
        if (elapsed() - t0 > half) break;
        const BayType &bt = state.bay_types[ti];
        for (double rot : test_angles) {
            if (elapsed() - t0 > half) break;
            double w = bt.width;
            double d = bt.depth + bt.gap;
            double y = state.wh.min_y;
            while (y + d <= state.wh.max_y + EPS) {
                if (elapsed() - t0 > half) break;
                double x = state.wh.min_x;
                bool row_placed = false;
                while (x + w <= state.wh.max_x + EPS) {
                    if (state.feasible(bt, x, y, rot)) {
                        state.add(bt, x, y, rot);
                        ++total;
                        x += w;
                        row_placed = true;
                    } else {
                        x += 50;
                    }
                }
                y += row_placed ? d : 50.0;
            }
        }
    }

    // Passes 2-6: candidate-based filling
    for (int pass = 0; pass < 5; ++pass) {
        if (elapsed() - t0 > time_limit) break;
        int placed_this_pass = 0;

        std::unordered_set<double> cxs_set(state.base_xs.begin(), state.base_xs.end());
        std::unordered_set<double> cys_set(state.base_ys.begin(), state.base_ys.end());
        for (int idx : state.active) {
            auto &b = state.bays[idx];
            cxs_set.insert(b.x1); cxs_set.insert(b.x2);
            cys_set.insert(b.y1); cys_set.insert(b.y2);
        }
        std::vector<double> sxs(cxs_set.begin(), cxs_set.end());
        std::vector<double> sys(cys_set.begin(), cys_set.end());
        std::sort(sxs.begin(), sxs.end());
        std::sort(sys.begin(), sys.end());

        for (int ti : sorted_idx) {
            if (elapsed() - t0 > time_limit) break;
            const BayType &bt = state.bay_types[ti];
            for (double rot : test_angles) {
                for (double y : sys) {
                    if (elapsed() - t0 > time_limit) break;
                    for (double x : sxs) {
                        if (state.feasible(bt, x, y, rot)) {
                            state.add(bt, x, y, rot);
                            ++total;
                            ++placed_this_pass;
                        }
                    }
                }
            }
        }
        if (placed_this_pass == 0) break;
    }

    std::cerr << "  Greedy: " << total << " bays, Q=" << state.quality() << "\n";
}

// ---------------------------------------------------------------------------
// Undo structures
// ---------------------------------------------------------------------------
enum MoveKind { MV_ADD, MV_REMOVE, MV_MOVE, MV_SWAP, MV_REPACK };

struct UndoInfo {
    MoveKind kind;
    // For ADD
    int new_idx = -1;
    // For REMOVE
    int rem_idx = -1; PlacedBay rem_pb;
    // For MOVE / SWAP
    int list_pos = -1;
    int old_tid = -1;
    double old_x = 0, old_y = 0, old_rot = 0;
    // For REPACK
    std::vector<std::pair<int,PlacedBay>> saved_bays;
    std::vector<int> added_indices;
};

static void do_undo(State &state, const UndoInfo &u, std::vector<int> &active_list) {
    switch (u.kind) {
    case MV_ADD:
        state.remove(u.new_idx);
        if (!active_list.empty()) active_list.pop_back();
        break;
    case MV_REMOVE: {
        // Re-add using raw_reinsert to preserve correct index
        state.raw_reinsert(u.rem_idx, u.rem_pb);
        active_list.push_back(u.rem_idx);
        if (u.list_pos >= 0 && u.list_pos < (int)active_list.size()-1) {
            std::swap(active_list[u.list_pos], active_list.back());
        }
        break;
    }
    case MV_MOVE:
    case MV_SWAP: {
        state.remove(u.new_idx);
        const BayType &bt = state.bay_types[u.old_tid];
        int restored = state.add(bt, u.old_x, u.old_y, u.old_rot);
        if (u.list_pos >= 0 && u.list_pos < (int)active_list.size())
            active_list[u.list_pos] = restored;
        break;
    }
    case MV_REPACK:
        for (int a : u.added_indices) state.remove(a);
        for (auto &[bid, pb] : u.saved_bays)
            state.raw_reinsert(bid, pb);
        active_list.clear();
        active_list.insert(active_list.end(), state.active.begin(), state.active.end());
        break;
    }
}

// ---------------------------------------------------------------------------
// Simulated Annealing
// ---------------------------------------------------------------------------
static double sa(State &state, double time_limit) {
    double t0 = elapsed();

    double best_q = state.quality();
    auto   best_snap = state.snapshot();
    double cur_q  = best_q;

    const auto &bay_types = state.bay_types;
    int n_types = (int)bay_types.size();

    // Efficiency-weighted type selection
    std::vector<double> cum_w(n_types);
    double wtot = 0;
    for (auto &bt : bay_types) wtot += bt.nLoads / bt.price;
    double acc = 0;
    for (int i = 0; i < n_types; ++i) {
        acc += (bay_types[i].nLoads / bay_types[i].price) / wtot;
        cum_w[i] = acc;
    }
    cum_w.back() = 1.0;

    auto pick_type = [&]() -> int {
        double r = rng.rand01();
        for (int i = 0; i < n_types; ++i) if (r <= cum_w[i]) return i;
        return n_types - 1;
    };

    // Sample T0
    auto sample_t0 = [&]() -> double {
        std::vector<double> diffs;
        for (int trial = 0; trial < 100; ++trial) {
            int ti = pick_type();
            const BayType &bt = bay_types[ti];
            double rot = rng.rand01() < 0.5 && !state.wh.wall_angles.empty()
                ? state.wh.wall_angles[rng.randi((int)state.wh.wall_angles.size())]
                : rng.rand01() * 360.0;
            double tx = state.wh.min_x + rng.rand01() * (state.wh.max_x - state.wh.min_x);
            double ty = state.wh.min_y + rng.rand01() * (state.wh.max_y - state.wh.min_y);
            if (state.feasible(bt, tx, ty, rot)) {
                int idx = state.add(bt, tx, ty, rot);
                diffs.push_back(std::abs(state.quality() - cur_q));
                state.remove(idx);
            }
        }
        if (diffs.empty()) return std::max(1.0, best_q * 0.3);
        std::sort(diffs.begin(), diffs.end());
        return std::max(1.0, 2.0 * diffs[diffs.size()/2]);
    };

    double T0   = sample_t0();
    double T    = T0;
    double max_iter = time_limit * 1000.0;
    double beta = (T0 / std::max(1e-6, T0 * 0.01) - 1.0) / std::max(1.0, max_iter);

    // Adaptive move probabilities [ADD, REMOVE, MOVE, SWAP, REPACK]
    double move_probs[5]    = {0.40, 0.10, 0.30, 0.15, 0.05};
    int    move_attempts[5] = {};
    int    move_accepts[5]  = {};

    auto update_probs = [&]() {
        double ratios[5];
        for (int i = 0; i < 5; ++i)
            ratios[i] = std::max(0.05, move_attempts[i] > 0
                ? (double)move_accepts[i] / move_attempts[i] : 0.05);
        double tot = 0; for (double r : ratios) tot += r;
        for (int i = 0; i < 5; ++i) move_probs[i] = ratios[i] / tot;
        std::memset(move_attempts, 0, sizeof(move_attempts));
        std::memset(move_accepts,  0, sizeof(move_accepts));
    };

    auto pick_move = [&](int n_active) -> int {
        if (n_active == 0) return 0;
        double r = rng.rand01(), s = 0;
        for (int i = 0; i < 5; ++i) { s += move_probs[i]; if (r <= s) return i; }
        return 4;
    };

    // Build wall angles list for SA
    std::vector<double> wall_ang = state.wh.wall_angles;
    if (wall_ang.empty()) wall_ang = {0,90,180,270};

    std::vector<int> active_list(state.active.begin(), state.active.end());
    int iters  = 0;
    int no_imp = 0;
    const int MAX_NO_IMP = 10000;

    while (elapsed() - t0 < time_limit) {
        ++iters;
        T = T0 / (1.0 + beta * iters);

        int n_active = (int)active_list.size();
        int m_type   = pick_move(n_active);
        ++move_attempts[m_type];

        if (iters % 1000 == 0) state.update_candidates();
        if (iters %  500 == 0) update_probs();

        UndoInfo undo;
        undo.kind = (MoveKind)m_type;
        bool valid = false;

        // ===== ADD =====
        if (m_type == MV_ADD) {
            int ti = pick_type();
            const BayType &bt = bay_types[ti];
            bool placed = false;

            // Strategy 1: adjacent to existing bay
            if (n_active > 0 && rng.rand01() < 0.75) {
                int ref_i = rng.randi(n_active);
                int ref_idx = active_list[ref_i];
                if (state.active.count(ref_idx)) {
                    auto &ref = state.bays[ref_idx];
                    std::vector<double> rots = {0,90};
                    if (rng.rand01() < 0.5) std::swap(rots[0], rots[1]);
                    for (double rot : rots) {
                        if (placed) break;
                        double w = bt.width, d = bt.depth + bt.gap;
                        double trials[8][2] = {
                            {ref.x2, ref.y1}, {ref.x1-w, ref.y1},
                            {ref.x1, ref.y2}, {ref.x1, ref.y1-d},
                            {ref.x2, ref.y2}, {ref.x1-w, ref.y2},
                            {ref.x2, ref.y2-d}, {ref.x1-w, ref.y1-d}
                        };
                        for (auto &t : trials) {
                            if (state.feasible(bt, t[0], t[1], rot)) {
                                int idx = state.add(bt, t[0], t[1], rot);
                                active_list.push_back(idx);
                                undo.new_idx = idx;
                                placed = true; valid = true;
                                break;
                            }
                        }
                    }
                }
            }

            // Strategy 2: candidate corners
            if (!placed && !state.candidate_corners.empty()) {
                auto ang_list = wall_ang;
                if ((int)ang_list.size() > 8) ang_list.resize(8);
                auto corners_copy = state.candidate_corners;
                std::shuffle(corners_copy.begin(), corners_copy.end(),
                             std::default_random_engine(rng.next()));
                int max_c = std::min(6, (int)corners_copy.size());
                for (double rot : ang_list) {
                    if (placed) break;
                    for (int ci = 0; ci < max_c; ++ci) {
                        if (state.feasible(bt, corners_copy[ci][0], corners_copy[ci][1], rot)) {
                            int idx = state.add(bt, corners_copy[ci][0], corners_copy[ci][1], rot);
                            active_list.push_back(idx);
                            undo.new_idx = idx;
                            placed = true; valid = true;
                            break;
                        }
                    }
                }
            }

            // Strategy 3: base coords
            if (!placed) {
                auto bxs = state.base_xs; std::shuffle(bxs.begin(), bxs.end(),
                    std::default_random_engine(rng.next()));
                auto bys = state.base_ys; std::shuffle(bys.begin(), bys.end(),
                    std::default_random_engine(rng.next()));
                auto ang_list = wall_ang;
                if ((int)ang_list.size() > 8) ang_list.resize(8);
                int mx = std::min(6, (int)bxs.size());
                int my = std::min(6, (int)bys.size());
                for (double rot : ang_list) {
                    if (placed) break;
                    for (int xi = 0; xi < mx && !placed; ++xi)
                        for (int yi = 0; yi < my && !placed; ++yi)
                            if (state.feasible(bt, bxs[xi], bys[yi], rot)) {
                                int idx = state.add(bt, bxs[xi], bys[yi], rot);
                                active_list.push_back(idx);
                                undo.new_idx = idx;
                                placed = true; valid = true;
                            }
                }
            }
        }

        // ===== REMOVE =====
        else if (m_type == MV_REMOVE && n_active > 0) {
            int ai  = rng.randi(n_active);
            int idx = active_list[ai];
            undo.rem_pb   = state.remove(idx);
            undo.rem_idx  = idx;
            undo.list_pos = ai;
            active_list[ai] = active_list.back();
            active_list.pop_back();
            valid = true;
        }

        // ===== MOVE =====
        else if (m_type == MV_MOVE && n_active > 0) {
            int ai  = rng.randi(n_active);
            int idx = active_list[ai];
            auto &pb = state.bays[idx];
            int    old_tid = pb.type_id;
            double ox = pb.x, oy = pb.y, orot = pb.rot;
            const BayType &bt = bay_types[old_tid];
            state.remove(idx);
            bool moved = false;

            // Try adjacent
            if (n_active > 1 && rng.rand01() < 0.5) {
                int ri = rng.randi(n_active - 1);
                int ref_idx = active_list[ri >= ai ? ri + 1 : ri];
                if (ref_idx < (int)state.bays.size() && state.active.count(ref_idx)) {
                    auto &ref = state.bays[ref_idx];
                    double ref_rot = ref.rot;
                    std::vector<double> test_rots = {
                        ref_rot, std::fmod(ref_rot+90, 360.0),
                        std::fmod(ref_rot+180,360.0), std::fmod(ref_rot+270,360.0)
                    };
                    for (double rot : test_rots) {
                        if (moved) break;
                        double w = bt.width, d = bt.depth + bt.gap;
                        // Compute AABB span for alignment
                        Quad tc = obb_corners(0,0,w,d,rot);
                        double tx1,ty1,tx2,ty2;
                        aabb_from_quad(tc, tx1,ty1,tx2,ty2);
                        double span_x = tx2-tx1, span_y = ty2-ty1;
                        double trials[4][2] = {
                            {ref.x2, ref.y1}, {ref.x1-span_x, ref.y1},
                            {ref.x1, ref.y2}, {ref.x1, ref.y1-span_y}
                        };
                        for (auto &t : trials) {
                            if (state.feasible(bt, t[0], t[1], rot)) {
                                int ni = state.add(bt, t[0], t[1], rot);
                                active_list[ai] = ni;
                                undo = {MV_MOVE, ni, -1, {}, ai, old_tid, ox, oy, orot};
                                moved = true; valid = true;
                                break;
                            }
                        }
                    }
                }
            }

            // Random nudge
            if (!moved) {
                for (int trial = 0; trial < 8 && !moved; ++trial) {
                    double rv  = rng.rand01();
                    double rot;
                    if (rv < 0.3 && !wall_ang.empty())
                        rot = wall_ang[rng.randi((int)wall_ang.size())];
                    else if (rv < 0.6)
                        rot = orot + (rng.rand01()-0.5)*45.0;
                    else
                        rot = rng.rand01()*360.0;
                    rot = std::fmod(std::round(rot/3.0)*3.0 + 360.0, 360.0);
                    double dx = (rng.rand01()-0.5)*1000.0;
                    double dy = (rng.rand01()-0.5)*1000.0;
                    double tx = ox+dx, ty = oy+dy;
                    if (state.feasible(bt, tx, ty, rot)) {
                        int ni = state.add(bt, tx, ty, rot);
                        active_list[ai] = ni;
                        undo = {MV_MOVE, ni, -1, {}, ai, old_tid, ox, oy, orot};
                        moved = true; valid = true;
                    }
                }
            }

            if (!moved) {
                // Restore original
                int ni = state.add(bt, ox, oy, orot);
                active_list[ai] = ni;
            }
        }

        // ===== SWAP =====
        else if (m_type == MV_SWAP && n_active > 0) {
            int ai      = rng.randi(n_active);
            int idx     = active_list[ai];
            auto &pb    = state.bays[idx];
            int old_tid = pb.type_id;
            double ox = pb.x, oy = pb.y, orot = pb.rot;
            int new_tid = pick_type();
            if (new_tid != old_tid) {
                const BayType &new_bt = bay_types[new_tid];
                state.remove(idx);
                bool swapped = false;
                auto ang_list = wall_ang;
                ang_list.insert(ang_list.begin(), orot);
                if ((int)ang_list.size() > 8) ang_list.resize(8);
                for (double rot : ang_list) {
                    if (state.feasible(new_bt, ox, oy, rot)) {
                        int ni = state.add(new_bt, ox, oy, rot);
                        active_list[ai] = ni;
                        undo = {MV_SWAP, ni, -1, {}, ai, old_tid, ox, oy, orot};
                        swapped = true; valid = true;
                        break;
                    }
                }
                if (!swapped) {
                    const BayType &old_bt = bay_types[old_tid];
                    int ni = state.add(old_bt, ox, oy, orot);
                    active_list[ai] = ni;
                }
            }
        }

        // ===== REPACK =====
        else if (m_type == MV_REPACK && n_active > 0) {
            int ai  = rng.randi(n_active);
            int idx = active_list[ai];
            auto &pb = state.bays[idx];
            double px_mid = (pb.x1 + pb.x2) * 0.5;
            double py_mid = (pb.y1 + pb.y2) * 0.5;
            double L = 4000.0, half_L = L * 0.5;
            double zx1 = px_mid-half_L, zx2 = px_mid+half_L;
            double zy1 = py_mid-half_L, zy2 = py_mid+half_L;

            // Gather bays in zone
            std::vector<int> to_remove;
            for (int bid : state.active) {
                auto &b = state.bays[bid];
                if (!(b.x2 < zx1 || b.x1 > zx2 || b.y2 < zy1 || b.y1 > zy2))
                    to_remove.push_back(bid);
            }

            undo.kind = MV_REPACK;
            for (int bid : to_remove) {
                undo.saved_bays.push_back({bid, state.bays[bid]});
                state.remove(bid);
                auto it = std::find(active_list.begin(), active_list.end(), bid);
                if (it != active_list.end()) active_list.erase(it);
            }

            // Re-greedy in zone
            double step = L / 8.0;
            std::vector<double> sxs, sys;
            for (int i = 0; i <= 8; ++i) { sxs.push_back(zx1+i*step); sys.push_back(zy1+i*step); }

            // Sort by efficiency ascending
            std::vector<int> sorted_idx;
            for (int i = 0; i < n_types; ++i) sorted_idx.push_back(i);
            std::sort(sorted_idx.begin(), sorted_idx.end(), [&](int a, int b) {
                return bay_types[a].efficiency < bay_types[b].efficiency;
            });

            auto ang_list = wall_ang;
            if ((int)ang_list.size() > 4) ang_list.resize(4);

            for (int ti : sorted_idx) {
                const BayType &bt = bay_types[ti];
                for (double rot : ang_list) {
                    for (double y : sys) for (double x : sxs) {
                        if (state.feasible(bt, x, y, rot)) {
                            int ni = state.add(bt, x, y, rot);
                            undo.added_indices.push_back(ni);
                            active_list.push_back(ni);
                        }
                    }
                }
            }
            valid = true;
        }

        if (!valid) continue;

        double new_q = state.quality();
        double delta = new_q - cur_q;

        bool accept = (delta < 0);
        if (!accept && T > 1e-12) {
            double prob = std::exp(-delta / T);
            accept = (rng.rand01() < prob);
        }

        if (accept) {
            cur_q = new_q;
            ++move_accepts[m_type];
            if (new_q < best_q) {
                best_q    = new_q;
                best_snap = state.snapshot();
                no_imp    = 0;
            } else {
                ++no_imp;
            }
        } else {
            do_undo(state, undo, active_list);
            ++no_imp;
        }

        if (no_imp > MAX_NO_IMP && T < 1e-5) break;
        if (no_imp > MAX_NO_IMP) {
            state.restore(best_snap);
            active_list.assign(state.active.begin(), state.active.end());
            cur_q  = best_q;
            T      = std::max(1e-4, T0 * 0.05);
            no_imp = 0;
        }

        if (iters % 100 == 0) {
            std::cout << "[METRIC] " << iters << ","
                      << (elapsed()-t0) << "," << T
                      << "," << cur_q << "," << best_q << "\n";
        }
    }

    state.restore(best_snap);
    double el = elapsed() - t0;
    std::cerr << "  SA: " << iters << " iters ("
              << (int)(iters/std::max(el,0.001)) << "/s), best Q=" << best_q << "\n";
    return best_q;
}

// ---------------------------------------------------------------------------
// Post-processing
// ---------------------------------------------------------------------------
static void post_process(State &state) {
    const double shifts[16][2] = {
        {-10,0},{10,0},{0,-10},{0,10},{-20,0},{20,0},{0,-20},{0,20},
        {-50,0},{50,0},{0,-50},{0,50},{-100,0},{100,0},{0,-100},{0,100}
    };
    const double d_rots[] = {-3,3,-6,6,-15,15,-30,30};

    std::vector<int> bays_list(state.active.begin(), state.active.end());
    for (int idx : bays_list) {
        if (!state.active.count(idx)) continue;
        PlacedBay pb = state.remove(idx);
        const BayType &bt = state.bay_types[pb.type_id];
        double ox = pb.x, oy = pb.y, orot = pb.rot;

        bool placed = false;
        for (auto &sh : shifts) {
            if (state.feasible(bt, ox+sh[0], oy+sh[1], orot)) {
                state.add(bt, ox+sh[0], oy+sh[1], orot);
                placed = true; break;
            }
        }
        if (!placed) {
            for (double dr : d_rots) {
                double nr = std::fmod(orot+dr+360.0, 360.0);
                if (state.feasible(bt, ox, oy, nr)) {
                    state.add(bt, ox, oy, nr);
                    placed = true; break;
                }
            }
        }
        if (!placed) state.add(bt, ox, oy, orot);
    }

    greedy(state, 3.0);
}

// ---------------------------------------------------------------------------
// Validate
// ---------------------------------------------------------------------------
static bool validate(const State &state) {
    bool ok = true;
    std::vector<int> blist(state.active.begin(), state.active.end());
    for (int i = 0; i < (int)blist.size(); ++i) {
        int ii = blist[i];
        const PlacedBay &bi = state.bays.at(ii);
        const BayType   &bt = state.bay_types[bi.type_id];
        if (!state.wh.obb_inside(bi.corners)) {
            std::cerr << "  FAIL: bay " << ii << " outside warehouse\n"; ok = false;
        }
        if (state.ceil.min_height(bi.x1, bi.x2) < bt.threshold - EPS) {
            std::cerr << "  FAIL: bay " << ii << " exceeds ceiling\n"; ok = false;
        }
        for (int oi = 0; oi < (int)state.obs_rects.size(); ++oi) {
            auto &o = state.obs_rects[oi];
            Quad oc = {{ {o[0],o[1]},{o[2],o[1]},{o[2],o[3]},{o[0],o[3]} }};
            if (sat_overlap(bi.corners, oc)) {
                std::cerr << "  FAIL: bay " << ii << " overlaps obstacle " << oi << "\n"; ok = false;
            }
        }
        for (int j = i+1; j < (int)blist.size(); ++j) {
            int jj = blist[j];
            const auto &bj = state.bays.at(jj);
            if (sat_overlap(bi.bay_corners, bj.corners) || sat_overlap(bj.bay_corners, bi.corners)) {
                std::cerr << "  FAIL: bay " << ii << " overlaps bay " << jj << " (non-gap area)\n"; ok = false;
            }
        }
    }
    if (ok) std::cerr << "  Validation OK (" << blist.size() << " bays)\n";
    return ok;
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------
static void write_output(const State &state, const std::string &path) {
    std::ofstream f(path);
    f << "Id, X, Y, Rotation\n";
    std::vector<int> sorted_active(state.active.begin(), state.active.end());
    std::sort(sorted_active.begin(), sorted_active.end());
    for (int idx : sorted_active) {
        const PlacedBay &b = state.bays.at(idx);
        auto fmt = [](double v) -> std::string {
            if (v == std::floor(v)) return std::to_string((long long)v);
            std::ostringstream os; os << v; return os.str();
        };
        f << b.type_id << ", " << fmt(b.x) << ", " << fmt(b.y)
          << ", " << b.rot << "\n";
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
int main(int argc, char **argv) {
    if (argc < 6) {
        std::cerr << "Usage: solver_flex <warehouse> <obstacles> <ceiling> <bay_types> <output>\n";
        return 1;
    }

    g_start = std::chrono::steady_clock::now();

    auto wh_raw   = parse_csv(argv[1], 2);
    auto obs_raw  = parse_csv(argv[2], 4);
    auto ceil_raw = parse_csv(argv[3], 2);
    auto bt_raw   = parse_csv(argv[4], 7);
    std::string out_path = argv[5];

    // Build bay types
    std::vector<BayType> bay_types;
    for (auto &r : bt_raw) {
        BayType bt;
        bt.id         = (int)r[0];
        bt.width      = r[1]; bt.depth  = r[2];
        bt.height     = r[3]; bt.gap    = r[4];
        bt.nLoads     = (int)r[5]; bt.price = r[6];
        bt.threshold  = bt.height;
        bt.efficiency = (bt.nLoads > 0) ? bt.price / bt.nLoads : 1e18;
        bay_types.push_back(bt);
    }

    Warehouse wh; wh.build(wh_raw);
    Ceiling   ceil; ceil.build(ceil_raw);

    // Build obstacle rects
    std::vector<std::array<double,4>> obs_rects;
    for (auto &r : obs_raw)
        obs_rects.push_back({r[0], r[1], r[0]+r[2], r[1]+r[3]});

    std::cerr << "  Warehouse: " << wh_raw.size() << " verts"
              << ", Obstacles: " << obs_rects.size()
              << ", Ceiling: " << ceil_raw.size() << " pts"
              << ", Types: " << bay_types.size() << "\n";
    for (auto &bt : bay_types)
        std::cerr << "    T" << bt.id << ": " << bt.width << "x" << bt.depth
                  << " h=" << bt.height << " eff=" << bt.efficiency << "\n";
    std::cerr << "  Warehouse area: " << wh.area << "\n";

    State state(bay_types, wh, obs_rects, ceil);

    // Phase 1: Greedy
    double greedy_time = std::min(12.0, TIME_LIMIT * 0.4);
    std::cerr << "Phase 1: Greedy (" << greedy_time << "s)...\n";
    greedy(state, greedy_time);

    // Phase 2: SA
    double remaining = TIME_LIMIT - elapsed();
    if (remaining > 6.0) {
        std::cerr << "Phase 2: SA (" << (remaining - 5.0) << "s)...\n";
        sa(state, remaining - 5.0);
    }

    // Phase 3: Post-process
    std::cerr << "Phase 3: Post-processing...\n";
    post_process(state);

    validate(state);
    double q_final = state.quality();
    std::cerr << "Final: " << state.active.size()
              << " bays, Q=" << q_final
              << ", time=" << elapsed() << "s\n";

    write_output(state, out_path);
    return 0;
}
