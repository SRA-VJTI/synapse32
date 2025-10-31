#!/bin/bash

# RISC-V CPU Formal Verification Script
# Easy-to-use interface for running different levels of verification

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMAL_DIR="$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print colored output
print_header() {
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_success() {
    echo -e "${GREEN}[PASS] $1${NC}"
}

print_error() {
    echo -e "${RED}[FAIL] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

print_info() {
    echo -e "${CYAN}[INFO] $1${NC}"
}

trim_string() {
    local var="$1"
    var="${var#"${var%%[![:space:]]*}"}"
    var="${var%"${var##*[![:space:]]}"}"
    printf '%s' "$var"
}

# Show usage
show_usage() {
    cat << EOF
RISC-V CPU Formal Verification Script

Usage: $0 [COMMAND] [OPTIONS]

COMMANDS:
  quick         Run quick verification (core instructions only)
  basic         Run basic verification (all instructions)
  system        Run system-level verification (memory, CSR, etc.)
  full          Run complete verification suite
  custom        Run custom test selection
  generate      Generate test configurations only
  clean         Clean verification output files
  status        Show last verification results
  help          Show this help message

OPTIONS:
  -j, --jobs N     Number of parallel jobs (default: auto-detect)
  -t, --timeout N  Timeout per test in seconds (default: 300)
  -v, --verbose    Verbose output
  -q, --quiet      Quiet output (errors only)
  --no-color       Disable colored output

EXAMPLES:
  $0 quick                    # Quick verification
  $0 basic -j 4              # Basic verification with 4 parallel jobs
  $0 system --timeout 600    # System verification with 10min timeout
  $0 full -v                 # Complete verification with verbose output
  $0 custom instructions     # Run only instruction tests

VERIFICATION LEVELS:
  QUICK   (~5 min):  Core arithmetic and logical instructions
  BASIC   (~15 min): All RV32I instructions
  SYSTEM  (~10 min): Memory consistency, CSR, pipeline checks
  FULL    (~30 min): Complete verification suite
EOF
}

# Check dependencies
check_dependencies() {
    local missing_deps=()

    if ! command -v sby &> /dev/null; then
        missing_deps+=("sby")
    fi

    if ! command -v yosys &> /dev/null; then
        missing_deps+=("yosys")
    fi

    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        print_info "Please install: sudo apt-get install sby yosys python3"
        exit 1
    fi
}

# Instruction test cache
INSTRUCTION_TESTS=()

# Load instruction tasks from the shared list
load_instruction_tests() {
    local list_file="$FORMAL_DIR/instructions/instruction_list.txt"
    local sby_file="$FORMAL_DIR/instructions/verify_instructions.sby"

    if [ ! -f "$list_file" ]; then
        print_error "Instruction list not found: $list_file"
        return 1
    fi

    if [ ! -f "$sby_file" ]; then
        print_error "Instruction verification file not found: $sby_file"
        return 1
    fi

    INSTRUCTION_TESTS=()
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="$(trim_string "$line")"
        if [ -n "$line" ]; then
            INSTRUCTION_TESTS+=("$line")
        fi
    done < "$list_file"

    if [ ${#INSTRUCTION_TESTS[@]} -eq 0 ]; then
        print_error "No instruction tests found in $list_file"
        return 1
    fi

    return 0
}

# Run quick verification (core instructions only)
run_quick() {
    print_header "QUICK VERIFICATION - Core Instructions"

    if ! load_instruction_tests; then
        return 1
    fi

    local sby_file="$FORMAL_DIR/instructions/verify_instructions.sby"
    local quick_candidates=(add sub addi and or xor lw sw beq jal)
    local quick_tests=()

    for task in "${quick_candidates[@]}"; do
        if printf '%s\n' "${INSTRUCTION_TESTS[@]}" | grep -qx "$task"; then
            quick_tests+=("$task")
        else
            print_warning "Skipping unavailable instruction test: $task"
        fi
    done

    local total=${#quick_tests[@]}
    if [ $total -eq 0 ]; then
        print_error "No quick instruction tests available."
        return 1
    fi

    local passed=0

    for task in "${quick_tests[@]}"; do
        print_info "Running instruction test: $task..."

        if run_single_test "$sby_file" "$task"; then
            print_success "$task PASSED"
            ((passed++))
        else
            print_error "$task FAILED"
        fi
    done

    print_header "QUICK VERIFICATION RESULTS"
    echo -e "Passed: ${GREEN}$passed${NC}/$total tests"

    if [ $passed -eq $total ]; then
        print_success "All quick tests PASSED!"
        return 0
    else
        print_error "Some quick tests FAILED!"
        return 1
    fi
}

# Run basic verification (all instructions)
run_basic() {
    print_header "BASIC VERIFICATION - All Instructions"

    if ! load_instruction_tests; then
        return 1
    fi

    local sby_file="$FORMAL_DIR/instructions/verify_instructions.sby"
    local passed=0
    local total=${#INSTRUCTION_TESTS[@]}

    print_info "Running $total instruction tests..."

    for task in "${INSTRUCTION_TESTS[@]}"; do
        print_info "Running instruction test: $task..."

        if run_single_test "$sby_file" "$task"; then
            print_success "$task PASSED"
            ((passed++))
        else
            print_error "$task FAILED"
        fi
    done

    print_header "BASIC VERIFICATION RESULTS"
    echo -e "Passed: ${GREEN}$passed${NC}/$total tests"

    if [ $passed -eq $total ]; then
        print_success "All basic tests PASSED!"
        return 0
    else
        print_error "Some basic tests FAILED!"
        return 1
    fi
}

# Run system verification
run_system() {
    print_header "SYSTEM VERIFICATION - Memory, CSR, Pipeline"

    if [ ! -d "$FORMAL_DIR/system_checks" ]; then
        print_error "System checks directory not found!"
        return 1
    fi

    local test_files=($(find "$FORMAL_DIR/system_checks" -name "verify_*.sby" | sort))
    local passed=0
    local total=${#test_files[@]}

    print_info "Running $total system tests..."

    for test_file in "${test_files[@]}"; do
        local test_name=$(basename "$test_file" .sby)
        print_info "Running $test_name..."

        if run_single_test "$test_file"; then
            print_success "$test_name PASSED"
            ((passed++))
        else
            print_error "$test_name FAILED"
        fi
    done

    print_header "SYSTEM VERIFICATION RESULTS"
    echo -e "Passed: ${GREEN}$passed${NC}/$total tests"

    if [ $passed -eq $total ]; then
        print_success "All system tests PASSED!"
        return 0
    else
        print_error "Some system tests FAILED!"
        return 1
    fi
}

# Run full verification suite
run_full() {
    print_header "FULL VERIFICATION SUITE"

    cd "$FORMAL_DIR"
    print_info "Running complete verification suite with Python runner..."

    if python3 run_verification_suite.py "$@"; then
        print_success "Full verification suite COMPLETED!"
        return 0
    else
        print_error "Full verification suite encountered issues!"
        return 1
    fi
}

# Run single test
run_single_test() {
    local test_file="$1"
    local task="${2:-}"
    local timeout="${TIMEOUT:-300}"

    cd "$(dirname "$test_file")"

    local cmd=("sby" "-f" "$(basename "$test_file")")
    if [ -n "$task" ]; then
        cmd+=("$task")
    fi

    if [ "$VERBOSE" = "true" ]; then
        timeout "${timeout}s" "${cmd[@]}"
    elif [ "$QUIET" = "true" ]; then
        timeout "${timeout}s" "${cmd[@]}" >/dev/null 2>&1
    else
        timeout "${timeout}s" "${cmd[@]}" >/dev/null 2>&1
    fi

    return $?
}

# Clean verification files
clean_verification() {
    print_header "CLEANING VERIFICATION FILES"

    find "$FORMAL_DIR" -name "verify_*" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$FORMAL_DIR" -name "*.log" -delete 2>/dev/null || true
    find "$FORMAL_DIR" -name "verification_report.json" -delete 2>/dev/null || true

    print_success "Verification files cleaned"
}

# Show status of last run
show_status() {
    local report_file="$FORMAL_DIR/verification_report.json"

    if [ ! -f "$report_file" ]; then
        print_warning "No previous verification results found"
        print_info "Run verification first to see status"
        return 1
    fi

    print_header "LAST VERIFICATION STATUS"

    if command -v jq &> /dev/null; then
        local total=$(jq '.summary.total_tests' "$report_file")
        local passed=$(jq '.results | map(select(.status == "PASS")) | length' "$report_file")
        local failed=$(jq '.results | map(select(.status == "FAIL")) | length' "$report_file")
        local errors=$(jq '.results | map(select(.status == "ERROR")) | length' "$report_file")
        local timeouts=$(jq '.results | map(select(.status == "TIMEOUT")) | length' "$report_file")

        echo -e "Total Tests: $total"
        echo -e "[PASS] Passed:   ${GREEN}$passed${NC}"
        echo -e "[FAIL] Failed:   ${RED}$failed${NC}"
        echo -e "[ERROR] Errors:   ${RED}$errors${NC}"
        echo -e "[TIMEOUT] Timeouts: ${YELLOW}$timeouts${NC}"

        if [ "$failed" -gt 0 ] || [ "$errors" -gt 0 ] || [ "$timeouts" -gt 0 ]; then
            echo -e "\n${RED}Failed Tests:${NC}"
            jq -r '.results[] | select(.status != "PASS") | "\(.category)/\(.test_name): \(.status)"' "$report_file"
        fi
    else
        print_info "Install 'jq' for detailed status parsing"
        print_info "Report available at: $report_file"
    fi
}

# Parse command line arguments
VERBOSE=false
QUIET=false
JOBS=""
TIMEOUT=""
NO_COLOR=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -j|--jobs)
            JOBS="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        --no-color)
            NO_COLOR=true
            # Disable colors
            RED=""
            GREEN=""
            YELLOW=""
            BLUE=""
            PURPLE=""
            CYAN=""
            NC=""
            shift
            ;;
        -h|--help|help)
            show_usage
            exit 0
            ;;
        *)
            COMMAND="$1"
            shift
            break
            ;;
    esac
done

# Main execution
main() {
    case "${COMMAND:-help}" in
        quick)
            check_dependencies
            run_quick
            ;;
        basic)
            check_dependencies
            run_basic
            ;;
        system)
            check_dependencies
            run_system
            ;;
        full)
            check_dependencies
            run_full "$@"
            ;;
        custom)
            check_dependencies
            print_header "CUSTOM VERIFICATION"
            print_info "Running custom test selection: $*"
            cd "$FORMAL_DIR"
            python3 run_verification_suite.py --categories "$@"
            ;;
        generate)
            print_header "GENERATING TEST CONFIGURATIONS"
            print_info "Instruction tests are maintained via instruction_list.txt."
            print_info "No additional generation step is required."
            ;;
        clean)
            clean_verification
            ;;
        status)
            show_status
            ;;
        help|"")
            show_usage
            ;;
        *)
            print_error "Unknown command: $COMMAND"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
