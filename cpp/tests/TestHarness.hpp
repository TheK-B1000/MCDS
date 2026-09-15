#pragma once

// A ~70-line test harness. The project deliberately has no external test
// dependency: there is no package manager available here, and a course project
// gains nothing from GoogleTest that this does not already provide.
//
// Usage:
//
//     #include "TestHarness.hpp"
//     MCDS_TEST(my_case) {
//         MCDS_CHECK(1 + 1 == 2);
//         MCDS_CHECK_EQ(size, 3u);
//     }
//     MCDS_TEST_MAIN()

#include <cstdio>
#include <exception>
#include <functional>
#include <sstream>
#include <string>
#include <vector>

namespace mcds::test {

class Registry {
public:
    static Registry& instance() {
        static Registry registry;
        return registry;
    }

    void add(const char* name, std::function<void()> body) { cases_.push_back({name, std::move(body)}); }

    void fail(const char* file, int line, const std::string& message) {
        ++caseFailures_;
        ++totalFailures_;
        std::printf("  FAIL %s:%d  %s\n", file, line, message.c_str());
    }

    /// Returns a process exit code: 0 when every case passed.
    int run() {
        int passed = 0;
        for (const Case& c : cases_) {
            caseFailures_ = 0;
            try {
                c.body();
            } catch (const std::exception& e) {
                fail(__FILE__, __LINE__, std::string("unexpected exception: ") + e.what());
            } catch (...) {
                fail(__FILE__, __LINE__, "unexpected non-standard exception");
            }
            if (caseFailures_ == 0) {
                ++passed;
                std::printf("[ ok ] %s\n", c.name.c_str());
            } else {
                std::printf("[FAIL] %s (%d check failures)\n", c.name.c_str(), caseFailures_);
            }
        }
        std::printf("\n%d/%zu cases passed, %d check failures\n", passed, cases_.size(), totalFailures_);
        return totalFailures_ == 0 ? 0 : 1;
    }

private:
    struct Case {
        std::string name;
        std::function<void()> body;
    };

    std::vector<Case> cases_;
    int caseFailures_ = 0;
    int totalFailures_ = 0;
};

template <typename T>
std::string describe(const T& value) {
    std::ostringstream out;
    out << value;
    return out.str();
}

}  // namespace mcds::test

#define MCDS_TEST(name)                                                           \
    static void name();                                                           \
    namespace {                                                                   \
    struct Register_##name {                                                      \
        Register_##name() { ::mcds::test::Registry::instance().add(#name, name); } \
    };                                                                            \
    const Register_##name register_instance_##name;                                \
    }                                                                             \
    static void name()

#define MCDS_CHECK(condition)                                                                       \
    do {                                                                                            \
        if (!(condition)) {                                                                         \
            ::mcds::test::Registry::instance().fail(__FILE__, __LINE__, "CHECK failed: " #condition); \
        }                                                                                           \
    } while (false)

#define MCDS_CHECK_EQ(actual, expected)                                                                     \
    do {                                                                                                    \
        const auto mcds_actual = (actual);                                                                   \
        const auto mcds_expected = (expected);                                                               \
        if (!(mcds_actual == mcds_expected)) {                                                              \
            ::mcds::test::Registry::instance().fail(__FILE__, __LINE__,                                     \
                                                   std::string("CHECK_EQ failed: " #actual " == " #expected \
                                                               " (got ") +                                  \
                                                       ::mcds::test::describe(mcds_actual) + ", expected " + \
                                                       ::mcds::test::describe(mcds_expected) + ")");         \
        }                                                                                                   \
    } while (false)

#define MCDS_CHECK_THROWS(statement)                                                                    \
    do {                                                                                                \
        bool mcds_threw = false;                                                                         \
        try {                                                                                           \
            statement;                                                                                  \
        } catch (...) {                                                                                 \
            mcds_threw = true;                                                                           \
        }                                                                                               \
        if (!mcds_threw) {                                                                               \
            ::mcds::test::Registry::instance().fail(__FILE__, __LINE__,                                  \
                                                   "expected an exception from: " #statement);           \
        }                                                                                               \
    } while (false)

#define MCDS_TEST_MAIN() \
    int main() { return ::mcds::test::Registry::instance().run(); }
