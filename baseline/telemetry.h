#ifndef BASELINE_TELEMETRY_H
#define BASELINE_TELEMETRY_H
#include <array>
#include <atomic>
#include <chrono>
#include <vector>
#include <string>
#include <opencv2/core.hpp>

namespace baseline {
enum Stage { decode, grayscale, mask, rows, tear, fps_frametime, conversion,
             composition, rendering, csv_export, image_export, total_frame, end_to_end, stage_count };
static const char* const names[] = {"decode","grayscale","mask","rows","tear","fps_frametime",
    "image_conversion","image_composition","rendering","csv_export","image_export","total_frame","end_to_end"};
struct Measurement { std::atomic<long long> ns{0}; std::atomic<long long> calls{0}; };
inline std::array<Measurement,stage_count>& measurements() { static std::array<Measurement,stage_count> m; return m; }
#ifdef BASELINE_PROFILE
class Scope {
    Stage stage; std::chrono::steady_clock::time_point start; bool running=true;
public:
    explicit Scope(Stage s):stage(s),start(std::chrono::steady_clock::now()){}
    void stop() { if (!running)return; running=false;
        const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
        measurements()[stage].ns.fetch_add(ns,std::memory_order_relaxed);
        measurements()[stage].calls.fetch_add(1,std::memory_order_relaxed);
    }
    ~Scope(){stop();}
};
#endif
struct Observation { cv::Mat gray_a,gray_b; std::vector<double> fractions;
    std::vector<int> counts; std::string branch; double contribution=0; };
inline std::array<Observation,3>& observations(){static std::array<Observation,3> a;return a;}
inline bool& observing(){static bool enabled=false;return enabled;}
inline int& video(){static thread_local int i=0;return i;}
struct VideoScope { int old; explicit VideoScope(int i):old(video()){video()=i;} ~VideoScope(){video()=old;} };
inline void gray(const cv::Mat&a,const cv::Mat&b){if(observing()){
    observations()[video()].gray_a=a.clone(); observations()[video()].gray_b=b.clone();}}
inline void rowdata(const cv::Mat&m,const std::vector<double>&f){if(observing()){
    auto&o=observations()[video()];o.fractions=f;o.counts.assign(m.rows,0);
    for(int y=0;y<m.rows;++y)for(int x=0;x<m.cols;++x){const auto&p=m.at<cv::Vec3b>(y,x);
        if(p[0]&&p[1]&&p[2])++o.counts[y];}
}}
inline double returned(const char* branch,double value){if(observing()){
    auto&o=observations()[video()];o.branch=branch;o.contribution=value;}return value;}
}
#ifdef BASELINE_PROFILE
#define BASE_SCOPE(variable,stage) baseline::Scope variable(baseline::stage)
#define BASE_STOP(variable) variable.stop()
#else
#define BASE_SCOPE(variable,stage) ((void)0)
#define BASE_STOP(variable) ((void)0)
#endif
#ifdef BASELINE_OBSERVE
#define BASE_VIDEO(index) baseline::VideoScope baseline_video_scope(index)
#define BASE_GRAY(a,b) baseline::gray(a,b)
#define BASE_ROWS(m,f) baseline::rowdata(m,f)
#define BASE_RETURN(branch,value) baseline::returned(branch,value)
#else
#define BASE_VIDEO(index) ((void)0)
#define BASE_GRAY(a,b) ((void)0)
#define BASE_ROWS(m,f) ((void)0)
#define BASE_RETURN(branch,value) (value)
#endif
#endif
